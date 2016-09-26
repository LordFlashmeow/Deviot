# !/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

import os
import sys
import glob
import sublime
import sublime_plugin
import subprocess
import threading
from shutil import rmtree

from .libs import Paths, Tools
from .libs.Menu import Menu
from .libs import PlatformioCLI
from .libs.Preferences import Preferences
from .libs.QuickPanel import quickPanel
from .libs import Libraries
from .libs.I18n import I18n
from .libs import Serial
from .libs import Messages
from .libs.Install import PioInstall
from .libs.Progress import ThreadProgress

_ = I18n().translate

package_name = 'Deviot'


def plugin_loaded():
    window = sublime.active_window()
    thread = threading.Thread(target=PioInstall(window).checkPio)
    thread.start()
    ThreadProgress(thread, _('processing'), _('done'))
    Tools.setStatus()
    Tools.userPreferencesStatus()


def plugin_unloaded():
    try:
        from package_control import events

        if events.remove(package_name):
            Tools.removePreferences()
    except:
        pass

# Compat with ST2
if(int(sublime.version()) < 3000):
    sublime.set_timeout(plugin_loaded, 300)
    unload_handler = plugin_unloaded


class DeviotListener(sublime_plugin.EventListener):
    """
    This is the first class to run when the plugin is excecuted
    Extends: sublime_plugin.EventListener
    """

    def on_activated(self, view):
        """
        Set the current version of Deviot

        Arguments: view {ST object} -- Sublime Text Object
        """
        PlatformioCLI.PlatformioCLI().checkIOT()
        Tools.setStatus()
        Tools.userPreferencesStatus()

    def on_selection_modified(self, view):
        region = view.sel()[0]
        region = view.line(region)
        text = view.substr(region)

        if 'error:' in text:
            text = text.split('error:')[0].strip()
            infos = text.split(':')

            if ':/' in text:
                file_path = infos[0] + ':' + infos[1]
                infos.pop(0)
                infos.pop(0)
            else:
                file_path = infos[0]
                infos.pop(0)

            line_no = int(infos[0])
            column_no = int(infos[1])

            file_view = view.window().open_file(file_path)
            point = file_view.text_point(line_no, column_no)
            file_view.show(point)

    def on_close(self, view):
        """
        When a sketch is closed, temp files are deleted

        Arguments: view {ST object} -- Sublime Text Object
        """
        # Serial Monitor
        monitor_module = Serial
        if Messages.isMonitorView(view):
            name = view.name()
            serial_port = name.split('-')[1].strip()
            if serial_port in monitor_module.serials_in_use:
                cur_serial_monitor = monitor_module.serial_monitor_dict.get(
                    serial_port, None)
                if cur_serial_monitor:
                    cur_serial_monitor.stop()
                monitor_module.serials_in_use.remove(serial_port)

        # Remove cache
        keep_cache = Preferences().get('keep_cache', True)
        if(keep_cache):
            return

        file_path = Tools.getPathFromView(view)
        if(not file_path):
            return
        file_name = Tools.getNameFromPath(file_path, ext=False)
        tmp_path = Paths.getTempPath()
        tmp_all = os.path.join(tmp_path, '*')
        tmp_all = glob.glob(tmp_all)

        for content in tmp_all:
            if file_name in content:
                tmp_path = os.path.join(tmp_path, content)
                rmtree(tmp_path, ignore_errors=False)
                Preferences().set('builded_sketch', False)


class DeviotNewSketchCommand(sublime_plugin.WindowCommand):

    def run(self):
        caption = _('caption_new_sketch')
        self.window.show_input_panel(caption, '', self.on_done, None, None)

    def on_done(self, sketch_name):
        Paths.selectDir(self.window, key=sketch_name, func=Tools.createSketch)


class DeviotSelectBoardCommand(sublime_plugin.WindowCommand):
    """
    This class trigger two methods to know what board(s)
    were chosen and to store it in a preference file.

    Extends: sublime_plugin.WindowCommand
    """
    MENU_LIST = []

    def run(self):
        self.MENU_LIST = Menu().createBoardsMenu()
        quickPanel(self.MENU_LIST, self.on_done)

    def on_done(self, selected):
        if(selected != -1):
            board_id = self.MENU_LIST[selected][1].split(' | ')[1]
            Preferences().boardSelected(board_id)
            Tools.saveEnvironment(board_id)
            Tools.userPreferencesStatus()

    def is_enabled(self):
        return Preferences().get('enable_menu', False)


class SelectEnvCommand(sublime_plugin.WindowCommand):
    """
    Stores the environment option selected by the user in
    the preferences files

    Extends: sublime_plugin.WindowCommand
    """
    MENU_LIST = []

    def run(self):
        self.MENU_LIST = Menu().getEnvironments()
        quickPanel(self.MENU_LIST[0], self.on_done, index=self.MENU_LIST[1])

    def on_done(self, selected):
        if(selected != -1):
            env = self.MENU_LIST[0][selected][1].split(' | ')[1]
            Tools.saveEnvironment(env)
            Tools.userPreferencesStatus()
            programmer = Preferences().get('programmer', False)
            PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_enabled(self):
        return PlatformioCLI.C['IOT']


class SearchLibraryCommand(sublime_plugin.WindowCommand):
    """
    Command to search a library in the platformio API

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        caption = _('search_query')
        self.window.show_input_panel(caption, '', self.on_done, None, None)

    def on_done(self, result):
        Libraries.openInThread('download', self.window, result)


class ShowResultsCommand(sublime_plugin.WindowCommand):
    """
    The results of the SearchLibraryCommand query in a quick_panel.
    When one of the result is selected, it's installed by CLI

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        MENU_LIST = Libraries.Libraries().getList()
        quickPanel(MENU_LIST, self.on_done)

    def on_done(self, result):
        if(result != -1):
            Libraries.openInThread('install', self.window, result)


class RemoveLibraryCommand(sublime_plugin.WindowCommand):
    """
    Remove a library by the CLI

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        Libraries.openInThread('list', self.window)


class ShowRemoveListCommand(sublime_plugin.WindowCommand):
    """
    Show the list with all the installed libraries, and what you can remove

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        choose = Libraries.Libraries(
            self.window,
            feedback=False).installedList()
        quickPanel(choose, self.on_done)

    def on_done(self, result):
        if(result != -1):
            Libraries.openInThread('remove', self.window, result)


class ImportLibraryCommand(sublime_plugin.WindowCommand):
    """
    Shows the list with the availables libraries in deviot using quick panel

    Extends: sublime_plugin.WindowCommand
    """
    MENU_LIST = []

    def run(self):
        self.MENU_LIST = Menu().createLibraryImportMenu()
        quickPanel(self.MENU_LIST, self.on_done)

    def on_done(self, selection):
        if(selection > 0):
            path = self.MENU_LIST[selection][1]
            self.window.run_command('add_library', {'path': path})


class AddLibraryCommand(sublime_plugin.TextCommand):
    """
    Include the header(s) from the selected library into a sketch

    Extends: sublime_plugin.TextCommand
    """

    def run(self, edit, path):
        Tools.addLibraryToSketch(self.view, edit, path)


class ListLibraryExamplesCommand(sublime_plugin.WindowCommand):
    """
    Shows the list with examples of the availables libraries in
    deviot using quick panel

    Extends: sublime_plugin.WindowCommand
    """
    MENU_LIST = []

    def run(self):
        self.MENU_LIST = Menu().createLibraryExamplesMenu()
        quickPanel(self.MENU_LIST, self.on_done)

    def on_done(self, selection):
        if(selection > 0):
            path = self.MENU_LIST[selection][1]
            self.window.run_command('list_examples', {'path': path})


class ListExamplesCommand(sublime_plugin.WindowCommand):
    """
    Shows the list with the available examples in the library

    Extends: sublime_plugin.WindowCommand
    """
    MENU_LIST = []

    def run(self, path):

        self.MENU_LIST = [[_("select_example").upper()], [_("_previous")]]

        file_examples = os.path.join(path, '*')
        file_examples = glob.glob(file_examples)

        for file in file_examples:
            caption = os.path.basename(file)
            self.MENU_LIST.append([caption, file])

        quickPanel(self.MENU_LIST, self.on_done)

    def on_done(self, selection):
        if(selection == 1):
            self.window.run_command("list_library_examples")
            return

        if(selection > 0):
            path = self.MENU_LIST[selection][1]
            Tools.openExample(path, self.window)


class OpenLibraryFolderCommand(sublime_plugin.TextCommand):
    """
    Open a new window where the user libreries must be installed

    Extends: sublime_plugin.TextCommand
    """

    def run(self, edit):
        library = Paths.getPioLibrary()
        url = Paths.getOpenFolderPath(library)
        sublime.run_command('open_url', {'url': url})


class ExtraLibraryFolderCommand(sublime_plugin.WindowCommand):
    """
    Adds the path to the folder where search extra libraries
    """

    def run(self):
        Paths.selectDir(self.window, key='extra_lib', func=Preferences().set)


class RemoveExtraLibraryFolderCommand(sublime_plugin.WindowCommand):
    """
    Removes the path of the extra library
    """

    def run(self):
        Preferences().set('extra_lib', False)

    def is_enabled(self):
        if(Preferences().get('extra_lib', False)):
            return True
        else:
            return False


class BuildSketchCommand(sublime_plugin.TextCommand):
    """
    Trigger a method to build the files in the current
    view, initializes the console to show the state of
    the process

    Extends: sublime_plugin.TextCommand
    """

    def run(self, edit):
        if(Tools.ERRORS_LIST):
            Tools.ERRORS_LIST = Tools.highlightRemove(Tools.ERRORS_LIST)

        PlatformioCLI.PlatformioCLI().openInThread('build')

    def is_enabled(self):
        return Preferences().get('enable_menu', False)


class UploadSketchCommand(sublime_plugin.TextCommand):
    """
    Trigger a method to upload the files in the current
    view, initializes the console to show the state of
    the process

    Extends: sublime_plugin.TextCommand
    """

    def run(self, edit):
        if(Tools.ERRORS_LIST):
            Tools.ERRORS_LIST = Tools.highlightRemove(Tools.ERRORS_LIST)

        PlatformioCLI.C['PORTSLIST'] = None
        PlatformioCLI.PlatformioCLI().openInThread('upload')

    def is_enabled(self):
        return Preferences().get('enable_menu')


class CleanSketchCommand(sublime_plugin.TextCommand):
    """
    Trigger a method to delete firmware/program binaries compiled
    if a sketch has been built previously

    Extends: sublime_plugin.TextCommand
    """

    def run(self, edit):
        PlatformioCLI.PlatformioCLI().openInThread('clean')

    def is_enabled(self):
        is_enabled = Preferences().get('enable_menu', False)
        if(is_enabled):
            view = sublime.active_window().active_view()
            is_enabled = Tools.isIOTFile(view.file_name())
        return is_enabled


class OpenIniFileCommand(sublime_plugin.WindowCommand):

    def run(self):

        if(not PlatformioCLI.C['IOT']):
            return

        views = []
        path = Tools.getInitPath(self.window.active_view())
        view = self.window.open_file(path)
        views.append(view)
        if views:
            self.window.focus_view(views[0])

    def is_enabled(self):
        return PlatformioCLI.C['IOT']


class HideConsoleCommand(sublime_plugin.WindowCommand):
    """
    Hide the deviot console

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        self.window.run_command("hide_panel", {"panel": "output.exec"})


class ShowConsoleCommand(sublime_plugin.WindowCommand):
    """
    Hide the deviot console

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        self.window.run_command("show_panel", {"panel": "output.exec"})


class ProgrammerNoneCommand(sublime_plugin.WindowCommand):

    def run(self, programmer):
        Preferences().set('programmer', programmer)
        PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_checked(self, programmer):
        prog = Preferences().get('programmer', False)
        return prog == programmer

    def is_enabled(self, programmer):
        file = self.window.active_view().file_name()
        return Tools.isIOTFile(file)


class ProgrammerAvrCommand(sublime_plugin.WindowCommand):

    def run(self, programmer):
        Preferences().set('programmer', programmer)
        PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_checked(self, programmer):
        prog = Preferences().get('programmer', False)
        return prog == programmer

    def is_enabled(self, programmer):
        file = self.window.active_view().file_name()
        return Tools.isIOTFile(file)


class ProgrammerAvrMkiiCommand(sublime_plugin.WindowCommand):

    def run(self, programmer):
        Preferences().set('programmer', programmer)
        PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_checked(self, programmer):
        prog = Preferences().get('programmer', False)
        return prog == programmer

    def is_enabled(self, programmer):
        file = self.window.active_view().file_name()
        return Tools.isIOTFile(file)


class ProgrammerUsbTyniCommand(sublime_plugin.WindowCommand):

    def run(self, programmer):
        Preferences().set('programmer', programmer)
        PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_checked(self, programmer):
        prog = Preferences().get('programmer', False)
        return prog == programmer

    def is_enabled(self, programmer):
        file = self.window.active_view().file_name()
        return Tools.isIOTFile(file)


class ProgrammerArduinoIspCommand(sublime_plugin.WindowCommand):

    def run(self, programmer):
        Preferences().set('programmer', programmer)
        PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_checked(self, programmer):
        prog = Preferences().get('programmer', False)
        return prog == programmer

    def is_enabled(self, programmer):
        file = self.window.active_view().file_name()
        return Tools.isIOTFile(file)


class ProgrammerUsbaspCommand(sublime_plugin.WindowCommand):

    def run(self, programmer):
        Preferences().set('programmer', programmer)
        PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_checked(self, programmer):
        prog = Preferences().get('programmer', False)
        return prog == programmer

    def is_enabled(self, programmer):
        file = self.window.active_view().file_name()
        return Tools.isIOTFile(file)


class ProgrammerParallelCommand(sublime_plugin.WindowCommand):

    def run(self, programmer):
        Preferences().set('programmer', programmer)
        PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_checked(self, programmer):
        prog = Preferences().get('programmer', False)
        return prog == programmer

    def is_enabled(self, programmer):
        file = self.window.active_view().file_name()
        return Tools.isIOTFile(file)


class ProgrammerArduinoAsIspCommand(sublime_plugin.WindowCommand):

    def run(self, programmer):
        Preferences().set('programmer', programmer)
        PlatformioCLI.PlatformioCLI().programmer(programmer)

    def is_checked(self, programmer):
        prog = Preferences().get('programmer', False)
        return prog == programmer

    def is_enabled(self, programmer):
        file = self.window.active_view().file_name()
        return Tools.isIOTFile(file)


class SelectPortCommand(sublime_plugin.WindowCommand):
    """
    Saves the port COM selected by the user in the
    preferences file.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        PlatformioCLI.C['PORTSLIST'] = None
        listports = PlatformioCLI.PlatformioCLI().selectPort
        PlatformioCLI.PlatformioCLI().openInThread(listports)


class AddSerialIpCommand(sublime_plugin.WindowCommand):
    """
    Add a IP to the list of COM ports

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        caption = _('add_ip_caption')
        self.window.show_input_panel(caption, '', self.on_done, None, None)

    def on_done(self, result):
        if(result != -1):
            result = (result if result != 0 else '')
            Preferences().set('id_port', result)
            Preferences().set('port_bar', result)


class AuthChangeCommand(sublime_plugin.WindowCommand):
    """
    Saves the password to use in OTA Upload

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        self.window.show_input_panel(_("pass_caption"), '',
                                     self.on_done,
                                     None,
                                     None)

    def on_done(self, password):
        Preferences().set('auth', password)

    def is_enabled(self):
        return PlatformioCLI.PlatformioCLI().mDNSCheck(feedback=False)


class SerialMonitorRunCommand(sublime_plugin.WindowCommand):
    """
    Run a selected serial monitor and show the messages in a new window

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        if(not Preferences().get('id_port', False)):
            PlatformioCLI.PlatformioCLI().monitorCall()
        self.on_done()

    def on_done(self):
        Tools.toggleSerialMonitor(self.window)

    def is_checked(self):
        state = False
        monitor_module = Serial
        serial_port = Preferences().get('id_port', '')
        if serial_port in monitor_module.serials_in_use:
            serial_monitor = monitor_module.serial_monitor_dict.get(
                serial_port)
            if serial_monitor and serial_monitor.isRunning():
                state = True
        return state


class SendMessageSerialCommand(sublime_plugin.WindowCommand):
    """
    Send a text over the selected serial port

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        caption = _('send')
        self.window.show_input_panel(
            caption, '', self.on_done, None, self.on_cancel)

    def on_done(self, text):
        if(text):
            Tools.sendSerialMessage(text)
            self.window.run_command('send_message_serial')

    def on_cancel(self):
        view = self.window.find_output_panel('exec')
        region = sublime.Region(0, view.size())
        src_text = view.substr(region)
        if("Serial Monitor" in src_text):
            self.window.run_command("show_panel", {"panel": "output.exec"})


class DeviotOutputCommand(sublime_plugin.WindowCommand):
    """
    Select between use the deviot console as monitor serial or
    a normal window.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        output = Preferences().get('deviot_output', False)
        Preferences().set('deviot_output', not output)

    def is_checked(self):
        return Preferences().get('deviot_output', False)


class AutoScrollMonitorCommand(sublime_plugin.WindowCommand):
    """
    The scroll goes automatically to the last line when this option.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        keep = Preferences().get('auto_scroll', True)
        Preferences().set('auto_scroll', not keep)

    def is_checked(self):
        return Preferences().get('auto_scroll', True)


class ChooseBaudrateItemCommand(sublime_plugin.WindowCommand):
    """
    Stores the baudrate selected for the user and save it in
    the preferences file.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self, baudrate_item):
        Preferences().set('baudrate', baudrate_item)

    def is_checked(self, baudrate_item):
        target_baudrate = Preferences().get('baudrate', 9600)
        return baudrate_item == target_baudrate


class ChooseLineEndingItemCommand(sublime_plugin.WindowCommand):
    """
    Stores the Line ending selected for the user and save it in
    the preferences file.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self, line_ending_item):
        Preferences().set('line_ending', line_ending_item)

    def is_checked(self, line_ending_item):
        target_line_ending = Preferences().get('line_ending', '\n')
        return line_ending_item == target_line_ending


class ChooseDisplayModeItemCommand(sublime_plugin.WindowCommand):
    """
    Stores the display mode selected for the user and save it in
    the preferences file.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self, display_mode_item):
        Preferences().set('display_mode', display_mode_item)

    def is_checked(self, display_mode_item):
        target_display_mode = Preferences().get('display_mode', 'Text')
        return display_mode_item == target_display_mode


class UpgradePioCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        window = sublime.active_window()
        thread = threading.Thread(target=PioInstall(window, True).checkPio)
        thread.start()


class DeveloperPioCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        window = sublime.active_window()
        thread = threading.Thread(target=PioInstall(window, True).developer)
        thread.start()
        ThreadProgress(thread, _('processing'), _('done'))

    def is_checked(self):
        return Preferences().get('developer', False)


class ToggleVerboseCommand(sublime_plugin.WindowCommand):
    """
    Saves the verbose output option selected by the user in the
    preferences file.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        verbose = Preferences().get('verbose_output', False)
        Preferences().set('verbose_output', not verbose)

    def is_checked(self):
        return Preferences().get('verbose_output', False)


class RemoveUserFilesCommand(sublime_plugin.WindowCommand):

    def run(self):
        confirm = sublime.ok_cancel_dialog(
            _('confirm_del_pref'), _('continue'))

        if(confirm):
            Tools.removePreferences()


class KeepTempFilesCommand(sublime_plugin.WindowCommand):
    """
    When is select avoid to remove the cache from the temporal folder.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        keep = Preferences().get('keep_cache', True)
        Preferences().set('keep_cache', not keep)

    def is_checked(self):
        return Preferences().get('keep_cache', True)


class OpenBuildFolderCommand(sublime_plugin.TextCommand):
    """
    Open a new window where the user libreries must be installed

    Extends: sublime_plugin.TextCommand
    """

    def run(self, edit):
        temp = Paths.getTempPath()
        url = Paths.getOpenFolderPath(temp)
        sublime.run_command('open_url', {'url': url})


class ChangeBuildFolderCommand(sublime_plugin.WindowCommand):

    def run(self):
        Paths.selectDir(self.window, key='build_dir', func=Preferences().set)


class UseCppTemplateCommand(sublime_plugin.WindowCommand):

    def run(self):
        keep = Preferences().get('use_cpp', False)
        Preferences().set('use_cpp', not keep)

    def is_checked(self):
        return Preferences().get('use_cpp', False)


class UseAlwaysNativeCommand(sublime_plugin.WindowCommand):

    def run(self):
        keep = Preferences().get('force_native', False)
        Preferences().set('force_native', not keep)

    def is_checked(self):
        return Preferences().get('force_native', False)


class ChangeDefaultPathCommand(sublime_plugin.WindowCommand):
    """
    Set the default path when the "change folder" option is used

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        Paths.selectDir(self.window, key='default_path',
                        func=Preferences().set)


class RemoveDefaultPathCommand(sublime_plugin.WindowCommand):
    """
    Remove the default path when the "change folder" option is used

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        Preferences().set('default_path', False)


class SelectLanguageCommand(sublime_plugin.WindowCommand):

    def run(self, id_lang):
        restart = sublime.ok_cancel_dialog(_('restart_deviot'),
                                           _('continue_button'))

        if(restart):
            Preferences().set('id_lang', id_lang)
            Preferences().set('updt_menu', True)
            self.window.run_command('sublime_restart')

    def is_checked(self, id_lang):
        saved_id_lang = Preferences().get('id_lang')
        return saved_id_lang == id_lang


class DonateDeviotCommand(sublime_plugin.WindowCommand):
    """
    Show the Deviot github site.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        sublime.run_command('open_url', {'url': 'https://goo.gl/K0EpFU'})


class AboutDeviotCommand(sublime_plugin.WindowCommand):
    """
    Show the Deviot github site.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        sublime.run_command('open_url', {'url': 'https://goo.gl/c41EXS'})


class AboutPioCommand(sublime_plugin.WindowCommand):
    """
    Show the Deviot github site.

    Extends: sublime_plugin.WindowCommand
    """

    def run(self):
        sublime.run_command('open_url', {'url': 'http://goo.gl/KiXeZL'})


class AddStatusCommand(sublime_plugin.TextCommand):
    """
    Add a message in the status bar

    Extends: sublime_plugin.TextCommand
    """

    def run(self, edit, text, erase_time):
        Tools.setStatus(text, erase_time)


class SublimeRestartCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        if(sublime.platform() == 'windows'):
            if sublime.version()[:1] == '3':
                exec = os.path.join(os.getcwd(), 'sublime_text.exe')
                cmd = 'taskkill /im sublime_text.exe /f && cmd /C "%s"' % exec
                subprocess.call(cmd, shell=True)
            else:
                os.execl(sys.executable, ' ')
        elif(sublime.platform() == 'osx'):
            if sublime.version()[:1] == '3':
                exec = os.path.join(os.getcwd(), 'subl')
                cmd = 'pkill subl && "%s"' % exec
                subprocess.call(cmd, shell=True)
            else:
                os.execl(os.path.join(os.getcwd(), 'subl'))
        else:
            if sublime.version()[:1] == '3':
                exec = os.path.join(os.getcwd(), 'sublime_text')
                cmd = 'pkill  \'sublime_text\' && "%s"' % exec
                subprocess.call(cmd, shell=True)
            else:
                os.execl(os.path.join(os.getcwd(), 'sublime_text'))
