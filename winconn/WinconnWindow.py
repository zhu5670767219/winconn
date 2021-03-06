# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
'''
This file is part of WinConn http://stanev.org/winconn
Copyright (C) 2012 Alex Stanev <alex@stanev.org>

WinConn is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

WinConn is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with WinConn.  If not, see <http://www.gnu.org/licenses/>.
'''

import locale
from locale import gettext as _
locale.textdomain('winconn')

from gi.repository import Gtk, GObject, GLib # pylint: disable=E0611
import logging
logger = logging.getLogger('winconn')

from winconn_lib import Window
from winconn_lib.helpers import get_media_file
from winconn.AboutWinconnDialog import AboutWinconnDialog
from winconn import Commons

from collections import OrderedDict
from time import sleep
import tempfile

import os
import os.path
import sys
import threading
import gobject
import string
from sets import Set
from subprocess import Popen
from subprocess import PIPE
from subprocess import call
from shutil import rmtree

from winconn import prompts
            
# See winconn_lib.Window.py for more details about how this class works
class WinconnWindow(Window):
    class cmdThread(threading.Thread):
        proc = None
        stout = ''
        sterr = ''
        __xfec__ = dict([
            [-15, _('xfreerdp died unexpectedly')],
            [  0, _('Success')],
            [  1, _('Disconnect')],
            [  2, _('Logoff')],
            [  3, _('Idle timeout')],
            [  4, _('Logon timeout')],
            [  5, _('Connection replaced')],
            [  6, _('Out of memory')],
            [  7, _('Connection denied')],
            [  8, _('Connection denied FIPS')],
            [  9, _('Remote user does not have required privileges')],
            [ 10, _('Fresh credientials required')],
            [ 11, _('Disconnected by user')],
            [ 16, _('Internal')],
            [ 17, _('No license server')],
            [ 18, _('No license')],
            [ 19, _('Bad message from client')],
            [ 20, _('HWID does not match')],
            [ 21, _('Bad client')],
            [ 22, _('Can not finish protocol')],
            [ 23, _('Client ended protocol')],
            [ 24, _('Bad client encryption')],
            [ 25, _('Can not upgrade protocol')],
            [ 26, _('No remote connections allowed')],
            [ 32, _('RDP protocol error')],
            [128, _('Bad xfreerdp options. Consider filling a bug on Launchpad')],
            [129, _('xfreerdp out of memory')],
            [130, _('xfreerdp protocol error')],
            [131, _('Connection to server failed')]
        ])
        
        def __init__(self, app, cmd, widget):
            super(WinconnWindow.cmdThread, self).__init__()
            self.app = app
            self.cmd = cmd
            self.widget = widget
            self.quit = False
            
            logger.debug('Init app: %s', app)
        
        def setStatus(self, rc):
        
            logger.debug('rc: %i', rc)
            
            try:
                s = self.__xfec__[rc]
            except KeyError:
                s = _('Unknown return code {0}'.format(rc))
                
            if ''.join(self.stout).find('RAIL_EXEC_E_NOT_IN_ALLOWLIST') != -1:
                s = _('Application not in RemoteApp list. Check help to fix this.')
            elif ''.join(self.stout).find('RAIL_EXEC_E_FAIL') != -1:
                s = _('Could not execute remote application.')
                
            self.widget.set_text('{0}: {1}'.format(self.app, s))
            
            return False

        def run(self):
            self.proc = Popen(self.cmd, stdout=PIPE)
            while not self.quit:
                self.proc.poll()
                if self.proc.returncode is not None:
                    self.stout, self.sterr = self.proc.communicate()
                    GObject.idle_add(self.setStatus, self.proc.returncode)
                    return
                sleep(0.1)
             
    __gtype_name__ = 'WinconnWindow'
    common = None
    t = None
    sis = 'secondary-icon-stock'

    def readApps(self):
        for lApp in self.common.getApp():
            self.ui.lsApps.append(lApp)
            
    def initSecIco(self):
        for e in self.ui.grid:
            if isinstance(e, Gtk.Entry):
                e.set_property(self.sis, None)
    
    def checkApp(self, bypass=False):
        self.initSecIco()
        
        # check our input values
        valid = True
        # Name
        if self.common.get_App_opt('name') == '':
            self.ui.eName.set_property(self.sis, Gtk.STOCK_DIALOG_WARNING)
            valid = False
        
        # Name valid chars
        ac = Set(string.ascii_letters+string.digits+'_- ')
        if not Set(self.common.get_App_opt('name')).issubset(ac):
            self.ui.eName.set_property(self.sis, Gtk.STOCK_DIALOG_WARNING)
            valid = False
        
        # Name unique
        if not bypass:
            lAppNames = []
            for row in self.ui.lsApps:
                lAppNames.append(row[0])
                
            if self.ui.tsApp.count_selected_rows() == 1:
                # remove current name from list, we are updating
                tm, ti = self.ui.tsApp.get_selected()
                lAppNames.remove(tm.get_value(ti, 0))
                
            if self.common.get_App_opt('name') in lAppNames:
                self.ui.eName.set_property(self.sis, Gtk.STOCK_DIALOG_WARNING)
                valid = False

        # Application
        if self.common.get_App_opt('app') == '':
            self.ui.eApp.set_property(self.sis, Gtk.STOCK_DIALOG_WARNING)
            valid = False
            
        # Server
        if self.common.get_App_opt('server') == '':
            self.ui.eSrv.set_property(self.sis, Gtk.STOCK_DIALOG_WARNING)
            valid = False
        
        # Port
        try:
            p = int(self.common.get_App_opt('port'))
            if p <= 0 or p >= 65535:
                raise ValueError
        except ValueError:
            self.ui.ePort.set_property(self.sis, Gtk.STOCK_DIALOG_WARNING)
            valid = False
        
        # User
        if self.common.get_App_opt('user') == '':
            self.ui.eUser.set_property(self.sis, Gtk.STOCK_DIALOG_WARNING)
            valid = False
        
        # Folder
        if self.common.get_App_opt('folder') and not os.path.isdir(self.common.get_App_opt('folder')):
            self.ui.eFolder.set_property(self.sis, Gtk.STOCK_DIALOG_WARNING)
            valid = False
        
        return valid

    def showApp(self):
        self.ui.eName.set_text(self.common.get_App_opt('name'))
        self.ui.eApp.set_text(self.common.get_App_opt('app'))
        self.ui.eSrv.set_text(self.common.get_App_opt('server'))
        self.ui.ePort.set_text(self.common.get_App_opt('port'))
        self.ui.eUser.set_text(self.common.get_App_opt('user'))
        self.ui.ePass.set_text(self.common.get_App_opt('pass'))
        self.ui.eDomain.set_text(self.common.get_App_opt('domain'))
        self.ui.eFolder.set_text(self.common.get_App_opt('folder'))
        self.ui.sComp.set_active(self.common.get_App_opt('compress'))
        self.ui.sClip.set_active(self.common.get_App_opt('clipboard'))
        self.ui.sSound.set_active(self.common.get_App_opt('sound'))
        self.ui.sPrinter.set_active(self.common.get_App_opt('printer'))
        self.ui.sRFX.set_active(self.common.get_App_opt('remotefx'))

    def finish_initializing(self, builder): # pylint: disable=E1002
        """Set up the main window"""
        super(WinconnWindow, self).finish_initializing(builder)

        self.AboutDialog = AboutWinconnDialog
        
        # connect tree to values
        cell = Gtk.CellRendererText()
        col = self.ui.tvApps.get_column(0)        
        col.pack_start(cell, True)
        col.add_attribute (cell, 'text', 0)
        
        col = self.ui.tvApps.get_column(1)
        col.pack_start(cell, True)
        col.add_attribute (cell, 'text', 1)

        col = self.ui.tvApps.get_column(2)
        col.pack_start(cell, True)
        col.add_attribute (cell, 'text', 2)
        
        self.common = Commons.Commons()
        self.readApps()
        self.indicator.rebuild_menu(self)

    def tbExec_clicked(self, widget, bypass=False, row=None, data=None):
        if not bypass:
            if self.ui.tsApp.count_selected_rows() == 0:
                self.ui.lStatus.set_text(_('No application for execution selected'))
                return

        if not self.checkApp(bypass):
            self.ui.lStatus.set_text(_('Selected application has configuration errors'))
            return

        cmd = self.common.buildCmd()
        if cmd is not None:
            self.t = self.cmdThread(self.common.get_App_opt('name'), cmd, self.ui.lStatus)
            self.t.start()
        
    def tbNew_clicked(self, widget):
        self.initSecIco()
        self.ui.tsApp.unselect_all()
        self.common.init_App()
        self.showApp()
        self.ui.notebook.set_current_page(1)
        
    def tbDel_clicked(self, widget):
        tm, ti = self.ui.tsApp.get_selected()
        if ti is None:
            self.ui.lStatus.set_text(_('No application selected for deletion'))
            return

        appName = self.common.get_App_opt('name')
        response = prompts.yes_no('WinConn', _('Are you sure you want to delete {0} ?').format(appName))
        if response == Gtk.ResponseType.YES:
            self.launcher(appName, inst=False)
            self.launcher(appName, desktop=True, inst=False)
            self.common.delApp()
            self.ui.lsApps.remove(ti)
            self.indicator.rebuild_menu(self)

    def tbShortcut_clicked(self, widget, row=None, data=None):
        if self.ui.tsApp.count_selected_rows() == 0:
            self.ui.lStatus.set_text(_('No application selected to create desktop launcher'))
            return

        appName = self.common.get_App_opt('name')
        self.launcher(appName, desktop=True)

    def tbQuit_clicked(self, widget):
        self.destroy()
        
    def launcher(self, appName, desktop=False, inst=True):
        ret = True
        logger.debug('Launcher operation on app: %s', appName)
        if desktop:
            xdg_util = 'xdg-desktop-icon'
        else:
            xdg_util = 'xdg-desktop-menu'
            
        if inst:
            # create temp dir for our new desktop launcher
            try:
                # yeah, it's ugly
                template = '''[Desktop Entry]
Name={0}
Comment=WinConn RemoteApp {0}
Exec={1} -e "{0}"
Icon={2}
Terminal=false
Type=Application
'''

                # Application icon
                # FIXME: get real app icon in cache and link it here
                icon_path = get_media_file('winconn.png').replace('file:///', '')
                # executable path
                exec_path = os.path.join(sys.path[0], sys.argv[0])
                desktop_cont = template.format(appName, exec_path, icon_path)
                
                tdir = tempfile.mkdtemp(dir='/tmp')
                with open(tdir+'/winconn-application-'+appName+'.desktop', 'w') as dfile:
                    dfile.write(desktop_cont)
                rc = call([xdg_util, 'install', tdir+'/winconn-application-'+appName+'.desktop'])
                if rc:
                    ret = False
            except Exception as e:
                ret = False
                logger.debug('Install exception: %s', e)
            rmtree(tdir)
        else:
            try:
                rc = call([xdg_util, 'uninstall', 'winconn-application-'+appName+'.desktop'])
                if rc:
                    ret = False
            except Exception as e:
                ret = False
                logger.debug('Uninstall exception: %s', e)

        return ret

    def miImportRemmina_activate(self, widget):
        lAppNames = []
        for row in self.ui.lsApps:
            lAppNames.append(row[0])

        for lApp in self.common.importRemmina(lAppNames):
            # make sure we will save in new file
            sleep(0.001)
            self.common.setApp()
            self.ui.lsApps.append(self.common.get_App_opt())

        self.indicator.rebuild_menu(self)

        self.ui.lStatus.set_text(_('Remmina import finnished'))
        
    def miImportRDP_activate(self, widget):
        fcd = Gtk.FileChooserDialog(title = _('Select RDP file to import'),
                                    buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                    Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

        ff = Gtk.FileFilter()
        ff.set_name(_('Windows Remote Desktop files'))
        ff.add_pattern('*.rdp')
        fcd.add_filter(ff)

        response = fcd.run()
        rdpfile = fcd.get_filename()
        fcd.destroy()

        if rdpfile is None:
            return

        lAppNames = []
        for row in self.ui.lsApps:
            lAppNames.append(row[0])
        
        if self.common.importRDP(lAppNames, rdpfile):
            self.common.setApp()
            self.ui.lsApps.append(self.common.get_App_opt())
            self.indicator.rebuild_menu(self)
            self.ui.lStatus.set_text(_('RDP import succeessful'))
        else:
            self.ui.lStatus.set_text(_('RDP import unsuccessful'))

    def bSave_clicked(self, widget, data=None):
        # Save app name for later
        old_appName = self.common.get_App_opt('name')

        # Build our conf
        self.common.init_App()
        self.common.set_App_opt('name', self.ui.eName.get_text())
        self.common.set_App_opt('app', self.ui.eApp.get_text())
        self.common.set_App_opt('server', self.ui.eSrv.get_text())
        self.common.set_App_opt('port', self.ui.ePort.get_text())
        self.common.set_App_opt('user', self.ui.eUser.get_text())
        self.common.set_App_opt('pass', self.ui.ePass.get_text())
        self.common.set_App_opt('domain', self.ui.eDomain.get_text())
        self.common.set_App_opt('folder', self.ui.eFolder.get_text())
        self.common.set_App_opt('compress', self.ui.sComp.get_active())
        self.common.set_App_opt('clipboard', self.ui.sClip.get_active())
        self.common.set_App_opt('sound', self.ui.sSound.get_active())
        self.common.set_App_opt('printer', self.ui.sPrinter.get_active())
        self.common.set_App_opt('remotefx', self.ui.sRFX.get_active())

        if not self.checkApp():
            self.ui.lStatus.set_text(_('Please check your application configuration'))
            return

        tm, ti = self.ui.tsApp.get_selected()
        if ti is None:
            # this is a new savefile
            self.common.setApp()
            self.ui.lsApps.append(self.common.get_App_opt())
            self.ui.lStatus.set_text(_('New application added successfully'))
        else:
            # this is current App update
            # get conf, must be always the last col
            self.common.set_App_opt('conf', tm.get_value(ti, tm.get_n_columns()-1))
            lApp = self.common.get_App_opt()
            for i in range(0, tm.get_n_columns()-1):
                self.ui.lsApps.set_value(ti, i, lApp[i])
            self.common.setApp()
            self.ui.lStatus.set_text(_('Application updated successfully'))
        
        # Put app in menu, remove old if name changed
        appName = self.common.get_App_opt('name')
        if old_appName != appName:
            self.launcher(old_appName, inst=False)
        
        self.launcher(appName)            
        self.indicator.rebuild_menu(self)

    def bCancel_clicked(self, widget):
        self.ui.notebook.set_current_page(0)
        self.common.init_App()
        self.ui.tsApp.unselect_all()

    def tsApp_changed(self, widget):
        tm, ti = self.ui.tsApp.get_selected()
        if ti is None:
            return
        
        self.common.init_App()
        for i in range(0, tm.get_n_columns()):
            self.common.set_App_opt(i, tm.get_value(ti, i))

        self.showApp()
        self.checkApp()
        self.ui.notebook.set_current_page(1)
        self.ui.lStatus.set_text('')
        
    def eFolder_icon_press(self, widget, icon=None, data=None):
        response, path = prompts.choose_directory()
        if response == Gtk.ResponseType.OK:
            widget.set_text(path)
    
    def winconn_show(self, widget):
        self.present()
    
    def winconn_window_destroy(self, widget):
        if self.t is not None:
            self.t.quit = True
            
    def run_app(self, widget):
        app = widget.get_label()
        for row in self.ui.lsApps:
            if row[0] == app:
                for i in range(0, self.ui.tvApps.get_n_columns()):
                    self.common.set_App_opt(i, row[i])
                break

        self.tbExec_clicked(None, bypass=True)
