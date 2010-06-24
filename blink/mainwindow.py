# Copyright (C) 2010 AG Projects. See LICENSE for details.
#

from __future__ import with_statement

__all__ = ['MainWindow']

from PyQt4 import uic
from PyQt4.QtCore import Qt
from PyQt4.QtGui  import QBrush, QColor, QPainter, QPen, QPixmap

from application.notification import IObserver, NotificationCenter
from application.python.util import Null
from zope.interface import implements

from sipsimple.account import AccountManager, BonjourAccount

from blink.accounts import AccountModel, ActiveAccountModel
from blink.contacts import BonjourNeighbour, Contact, ContactGroup, ContactEditorDialog, ContactModel, ContactSearchModel
from blink.sessions import SessionManager, SessionModel
from blink.resources import Resources
from blink.util import run_in_gui_thread
from blink.widgets.buttons import SwitchViewButton


ui_class, base_class = uic.loadUiType(Resources.get('blink.ui'))

class MainWindow(base_class, ui_class):
    implements(IObserver)

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)

        with Resources.directory:
            self.setupUi(self)

        self.setWindowTitle('Blink')
        self.setWindowIconText('Blink')

        self.set_user_icon(Resources.get("icons/default-avatar.png")) # ":/resources/icons/default-avatar.png"
        self.enable_call_buttons(False)

        self.account_model = AccountModel(self)
        self.enabled_account_model = ActiveAccountModel(self.account_model, self)
        self.identity.setModel(self.enabled_account_model)

        self.contact_model = ContactModel(self)
        self.contact_search_model = ContactSearchModel(self.contact_model, self)
        self.contact_list.setModel(self.contact_model)
        self.search_list.setModel(self.contact_search_model)

        self.contact_list.selectionModel().selectionChanged.connect(self._SH_ContactListSelectionChanged)
        self.search_list.selectionModel().selectionChanged.connect(self._SH_SearchListSelectionChanged)
        self.search_box.textChanged.connect(self.contact_search_model.setFilterFixedString)

        self.contact_model.load()

        self.contact_editor = ContactEditorDialog(self.contact_model, self)

        self.session_model = SessionModel(self)
        self.session_list.setModel(self.session_model)

        self.session_list.selectionModel().selectionChanged.connect(self._SH_SessionListSelectionChanged)

        self.main_view.setCurrentWidget(self.contacts_panel)
        self.contacts_view.setCurrentWidget(self.contact_list_panel)
        self.search_view.setCurrentWidget(self.search_list_panel)

        self.conference_button.setEnabled(False)
        self.hangup_all_button.setEnabled(False)

        self.switch_view_button.viewChanged.connect(self._SH_SwitchViewButtonChangedView)

        self.search_box.textChanged.connect(self._SH_SearchBoxTextChanged)
        self.contact_model.itemsAdded.connect(self._SH_ContactModelAddedItems)
        self.contact_model.itemsRemoved.connect(self._SH_ContactModelRemovedItems)

        self.back_to_contacts_button.clicked.connect(self.search_box.clear) # this can be set in designer -Dan

        self.add_contact_button.clicked.connect(self._SH_AddContactButtonClicked)
        self.add_search_contact_button.clicked.connect(self._SH_AddContactButtonClicked)

        self.identity.activated[int].connect(self._SH_IdentityChanged)

        self.audio_call_button.clicked.connect(self._SH_AudioCallButtonClicked)
        self.contact_list.doubleClicked.connect(self._SH_ContactDoubleClicked) # activated is emitted on single click
        self.search_list.doubleClicked.connect(self._SH_ContactDoubleClicked) # activated is emitted on single click
        self.search_box.returnPressed.connect(self._SH_SearchBoxReturnPressed)

        self.session_model.sessionAdded.connect(self._SH_SessionModelAddedSession)
        self.session_model.structureChanged.connect(self._SH_SessionModelChangedStructure)
        self.hangup_all_button.clicked.connect(self._SH_HangupAllButtonClicked)
        self.conference_button.makeConference.connect(self._SH_MakeConference)
        self.conference_button.breakConference.connect(self._SH_BreakConference)

        notification_center = NotificationCenter()
        notification_center.add_observer(self, name='SIPApplicationWillStart')

    def set_user_icon(self, image_file_name):
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(Qt.transparent))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QBrush(Qt.white))
        painter.setPen(QPen(painter.brush(), 0, Qt.NoPen))
        #painter.drawRoundedRect(0, 0, 32, 32, 6, 6)
        painter.drawRoundedRect(0, 0, 32, 32, 0, 0)
        icon = QPixmap()
        if icon.load(image_file_name):
            icon = icon.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.drawPixmap(0, 0, icon)
        painter.end()
        self.image.setPixmap(pixmap)

    def enable_call_buttons(self, enabled):
        self.audio_call_button.setEnabled(enabled)
        self.im_session_button.setEnabled(enabled)
        self.ds_session_button.setEnabled(enabled)

    def _SH_AddContactButtonClicked(self, clicked):
        model = self.contact_model
        selected_items = ((index.row(), model.data(index)) for index in self.contact_list.selectionModel().selectedIndexes())
        try:
            item = (item for row, item in sorted(selected_items) if type(item) in (Contact, ContactGroup)).next()
            preferred_group = item if type(item) is ContactGroup else item.group
        except StopIteration:
            try:
                preferred_group = (group for group in model.contact_groups if type(group) is ContactGroup).next()
            except StopIteration:
                preferred_group = None
        self.contact_editor.open_for_add(self.search_box.text(), preferred_group)

    def _SH_AudioCallButtonClicked(self):
        list = self.contact_list if self.contacts_view.currentWidget() is self.contact_list_panel else self.search_list
        selected_indexes = list.selectionModel().selectedIndexes()
        contact = list.model().data(selected_indexes[0]) if selected_indexes else Null
        address = contact.uri or unicode(self.search_box.text())
        name = contact.name or None
        session_manager = SessionManager()
        session_manager.start_call(name, address, account=BonjourAccount() if isinstance(contact, BonjourNeighbour) else None)

    def _SH_BreakConference(self):
        active_session = self.session_model.data(self.session_list.selectionModel().selectedIndexes()[0])
        self.session_model.breakConference(active_session.conference)

    def _SH_ContactDoubleClicked(self, index):
        contact = index.model().data(index)
        if not isinstance(contact, Contact):
            return
        session_manager = SessionManager()
        session_manager.start_call(contact.name, contact.uri, account=BonjourAccount() if isinstance(contact, BonjourNeighbour) else None)

    def _SH_ContactListSelectionChanged(self, selected, deselected):
        account_manager = AccountManager()
        selected_items = self.contact_list.selectionModel().selectedIndexes()
        self.enable_call_buttons(account_manager.default_account is not None and len(selected_items)==1 and isinstance(self.contact_model.data(selected_items[0]), Contact))

    def _SH_ContactModelAddedItems(self, items):
        if self.search_box.text().isEmpty():
            return
        active_widget = self.search_list_panel if self.contact_search_model.rowCount() else self.not_found_panel
        self.search_view.setCurrentWidget(active_widget)

    def _SH_ContactModelRemovedItems(self, items):
        if self.search_box.text().isEmpty():
            return
        if any(type(item) is Contact for item in items) and self.contact_search_model.rowCount() == 0:
            self.search_box.clear()
        else:
            active_widget = self.search_list_panel if self.contact_search_model.rowCount() else self.not_found_panel
            self.search_view.setCurrentWidget(active_widget)

    def _SH_HangupAllButtonClicked(self):
        for session in self.session_model.sessions:
            session.end()

    def _SH_IdentityChanged(self, index):
        account_manager = AccountManager()
        account_manager.default_account = self.identity.itemData(index).toPyObject().account

    def _SH_MakeConference(self):
        self.session_model.conferenceSessions([session for session in self.session_model.sessions if session.conference is None and not session.pending_removal])

    def _SH_SearchBoxReturnPressed(self):
        address = unicode(self.search_box.text())
        session_manager = SessionManager()
        session_manager.start_call(None, address)

    def _SH_SearchBoxTextChanged(self, text):
        account_manager = AccountManager()
        if text:
            self.switch_view_button.view = SwitchViewButton.ContactView
            selected_items = self.search_list.selectionModel().selectedIndexes()
            self.enable_call_buttons(account_manager.default_account is not None and len(selected_items)==1)
        else:
            selected_items = self.contact_list.selectionModel().selectedIndexes()
            self.enable_call_buttons(account_manager.default_account is not None and len(selected_items)==1 and type(self.contact_model.data(selected_items[0])) is Contact)
            # switch to the sessions panel if there are active sessions, else to the contacts panel -Dan
        active_widget = self.contact_list_panel if text.isEmpty() else self.search_panel
        if active_widget is self.search_panel and self.contacts_view.currentWidget() is not self.search_panel:
            self.search_list.selectionModel().clearSelection()
        self.contacts_view.setCurrentWidget(active_widget)
        active_widget = self.search_list_panel if self.contact_search_model.rowCount() else self.not_found_panel
        self.search_view.setCurrentWidget(active_widget)

    def _SH_SearchListSelectionChanged(self, selected, deselected):
        account_manager = AccountManager()
        selected_items = self.search_list.selectionModel().selectedIndexes()
        self.enable_call_buttons(account_manager.default_account is not None and len(selected_items)==1)

    def _SH_SessionListSelectionChanged(self, selected, deselected):
        selected_indexes = selected.indexes()
        active_session = self.session_model.data(selected_indexes[0]) if selected_indexes else Null
        if active_session.conference:
            self.conference_button.setEnabled(True)
            self.conference_button.setChecked(True)
        else:
            self.conference_button.setEnabled(len([session for session in self.session_model.sessions if session.conference is None and not session.pending_removal]) > 1)
            self.conference_button.setChecked(False)

    def _SH_SessionModelAddedSession(self, session_item):
        if session_item.session.state is None:
            self.search_box.clear()

    def _SH_SessionModelChangedStructure(self):
        self.hangup_all_button.setEnabled(any(not session.pending_removal for session in self.session_model.sessions))
        selected_indexes = self.session_list.selectionModel().selectedIndexes()
        active_session = self.session_model.data(selected_indexes[0]) if selected_indexes else Null
        if active_session.conference:
            self.conference_button.setEnabled(True)
            self.conference_button.setChecked(True)
        else:
            self.conference_button.setEnabled(len([session for session in self.session_model.sessions if session.conference is None and not session.pending_removal]) > 1)
            self.conference_button.setChecked(False)

    def _SH_SwitchViewButtonChangedView(self, view):
        self.main_view.setCurrentWidget(self.contacts_panel if view is SwitchViewButton.ContactView else self.sessions_panel)

    @run_in_gui_thread
    def handle_notification(self, notification):
        handler = getattr(self, '_NH_%s' % notification.name, Null)
        handler(notification)

    def _NH_SIPApplicationWillStart(self, notification):
        account_manager = AccountManager()
        notification_center = NotificationCenter()
        notification_center.add_observer(self, sender=account_manager, name='SIPAccountManagerDidChangeDefaultAccount')

    def _NH_SIPAccountManagerDidChangeDefaultAccount(self, notification):
        if notification.data.account is None:
            self.enable_call_buttons(False)
        else:
            selected_items = self.contact_list.selectionModel().selectedIndexes()
            self.enable_call_buttons(len(selected_items)==1 and isinstance(self.contact_model.data(selected_items[0]), Contact))

del ui_class, base_class


