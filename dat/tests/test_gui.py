"""Tests for the dat.gui package.

"""


import unittest
import warnings

import dat.tests
from dat.tests import CallRecorder


class Test_gui(unittest.TestCase):
    def test_translate(self):
        """Tests the translate() mechanism.

        Doesn't actually checks that anything gets translated.
        """
        from PyQt4 import QtCore
        old_translate = QtCore.QCoreApplication.translate
        try:
            QtCore.QCoreApplication.translate = cr = CallRecorder(
                old_translate)

            from dat.gui import translate
            tr = translate(Test_gui)
            self.assertIsNotNone(tr)
            msg = u"Don't translate "
            msg += u"me (unittest)"  # there is no way xgettext can find this

            self.assertEqual(tr(msg), msg)
            call1 = (
                [
                    'dat.tests.test_gui.Test_gui',
                    msg,
                    None,
                    QtCore.QCoreApplication.UnicodeUTF8],
                dict())
            self.assertEqual(cr.calls, [call1])

            tr = translate('this test')
            self.assertEqual(tr(msg, "disambiguation"), msg)
            call2 = (
                [
                    'this test',
                    msg,
                    "disambiguation",
                    QtCore.QCoreApplication.UnicodeUTF8],
                dict())
            self.assertEqual(cr.calls, [call1, call2])
        finally:
            QtCore.QCoreApplication.translate = old_translate

    def test_notifications(self):
        """Tests the NotificationDispatcher class.
        """
        from dat.gui.application import NotificationDispatcher
        nd = NotificationDispatcher()

        class C(object):
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.resetwarnings()
            notif1 = CallRecorder()
            nd.register_notification('notif_A', notif1)
            # registered to non-existing notification
            self.assertEqual(len(w), 1)

            notif2 = CallRecorder()
            nd.register_notification('notif_A', notif2)

            nd.send_notification('notif_A', 'hello', 'world', rep=42)
            first_call = (['hello', 'world'], dict(rep=42))
            self.assertEqual(notif1.calls, [first_call])
            self.assertEqual(notif2.calls, [first_call])

            nd.unregister_notification('notif_A', notif2)
            nd.send_notification('notif_A', 'second', nb=2)
            second_call = (['second'], dict(nb=2))
            self.assertEqual(notif1.calls, [first_call, second_call])
            self.assertEqual(notif2.calls, [first_call])

            nd.builderWindow = C()
            viewA, viewB = C(), C()
            nd.builderWindow.current_view = viewA

            fakeWindow = C()
            nd.create_notification('notif_B')
            self.assertEqual(len(w), 1)
            nd.create_notification('notif_B')
            # notification created twice
            self.assertEqual(len(w), 2)
            nd.create_notification('notif_B', window=fakeWindow)
            nd.create_notification('notif_B', view=viewA)
            nd.create_notification('notif_B', view=viewB)
            notif3 = CallRecorder()
            nd.register_notification('notif_B', notif3,
                                     window=fakeWindow)
            notif4 = CallRecorder()
            self.assertEqual(len(w), 2)
            nd.register_notification('notif_B', notif4,
                                     window=nd.builderWindow)
            # registered to non-existing notification
            self.assertEqual(len(w), 3)
            notif5 = CallRecorder()
            nd.register_notification('notif_B', notif5)
            notif6 = CallRecorder()
            nd.register_notification('notif_B', notif6,
                                     view=viewA)
            notif7 = CallRecorder()
            nd.register_notification('notif_B', notif7,
                                     view=viewB)
            nd.send_notification('notif_B', 'third')
            third_call = (['third'], dict())

            self.assertEqual(notif1.calls, [first_call, second_call])
            self.assertEqual(notif2.calls, [first_call])
            self.assertEqual(notif3.calls, [])
            self.assertEqual(notif4.calls, [third_call])
            self.assertEqual(notif5.calls, [third_call])
            self.assertEqual(notif6.calls, [third_call])
            self.assertEqual(notif7.calls, [])

            self.assertEqual(len(w), 3)
            nd.unregister_notification('notif_A', notif7)
            # unregistered non-registered method
            self.assertEqual(len(w), 4)
            nd.unregister_notification('notif_B', notif6,
                                       view=viewA)
            nd.send_notification('notif_B', nb=4)
            self.assertEqual(len(w), 4)
            self.assertEqual(notif6.calls, [third_call])


class Test_advancedlineedit(unittest.TestCase):
    def setUp(self):
        self._app = dat.tests.setup_application()

    def tearDown(self):
        self._app.quit()
        self._app = None

    def test_validation(self):
        """Tests the validation logic.
        """
        from dat.gui.generic import AdvancedLineEdit
        le = AdvancedLineEdit("test",
                              validate=lambda t: t == "a")
        self._app.processEvents()
        self.assertEqual(le.text(), "test")
        self.assertFalse(le.isValid())
        self.assertEqual(le._choose_color(), "#DDAAAA")

        le.setText("a")
        self._app.processEvents()
        self.assertTrue(le.isValid())
        self.assertEqual(le._choose_color(), "#AADDAA")

    def test_default(self):
        """Tests the default value logic.
        """
        from dat.gui.generic import AdvancedLineEdit
        le = AdvancedLineEdit("test",
                              default="a")
        self._app.processEvents()
        self.assertEqual(le.text(), "test")
        self.assertFalse(le.isDefault())
        self.assertEqual(le._choose_color(), "#FFFFFF")

        le.reset()
        self._app.processEvents()
        self.assertEqual(le.text(), "a")
        self.assertTrue(le.isDefault())
        self.assertEqual(le._choose_color(), "#AAAADD")

    def test_basic(self):
        """Tests the widget without validation or default value.
        """
        from dat.gui.generic import AdvancedLineEdit
        le = AdvancedLineEdit("test")
        self._app.processEvents()
        self.assertEqual(le.text(), "test")
        self.assertEqual(le._choose_color(), "#FFFFFF")
        le.setText("42")
        self._app.processEvents()
        self.assertEqual(le.text(), "42")
        self.assertEqual(le._choose_color(), "#FFFFFF")

    def test_both_diff(self):
        """Tests the widget with both validation and default value.
        """
        from dat.gui.generic import AdvancedLineEdit
        le = AdvancedLineEdit("test",
                              default="b",
                              validate=lambda t: t == "a")
        self._app.processEvents()
        self.assertEqual(le.text(), "test")
        self.assertFalse(le.isDefault())
        self.assertFalse(le.isValid())
        self.assertEqual(le._choose_color(), "#DDAAAA")

        le.reset()
        self._app.processEvents()
        self.assertEqual(le.text(), "b")
        self.assertTrue(le.isDefault())
        self.assertFalse(le.isValid())
        self.assertEqual(le._choose_color(), "#DDAAAA")

        le.setText("a")
        self._app.processEvents()
        self.assertFalse(le.isDefault())
        self.assertTrue(le.isValid())
        self.assertEqual(le._choose_color(), "#AADDAA")

    def test_both_diff_flag_default(self):
        """Tests that the correct logic gets used with COLOR_DEFAULTVALUE.
        """
        from dat.gui.generic import AdvancedLineEdit
        le = AdvancedLineEdit("test",
                              default="b",
                              validate=lambda t: t == "a",
                              flags=AdvancedLineEdit.COLOR_DEFAULTVALUE)
        self._app.processEvents()
        self.assertFalse(le.isDefault())
        self.assertFalse(le.isValid())
        self.assertEqual(le._choose_color(), "#FFFFFF")

        le.reset()
        self._app.processEvents()
        self.assertEqual(le.text(), "b")
        self.assertTrue(le.isDefault())
        self.assertFalse(le.isValid())
        self.assertEqual(le._choose_color(), "#AAAADD")

    def test_both_diff_flag_valid(self):
        """Tests that the correct logic gets used with COLOR_VALIDITY.
        """
        from dat.gui.generic import AdvancedLineEdit
        le = AdvancedLineEdit("test",
                              default="b",
                              validate=lambda t: t == "b",
                              flags=AdvancedLineEdit.COLOR_VALIDITY)
        self._app.processEvents()
        self.assertFalse(le.isDefault())
        self.assertFalse(le.isValid())
        self.assertEqual(le._choose_color(), "#DDAAAA")

        le.reset()
        self._app.processEvents()
        self.assertEqual(le.text(), "b")
        self.assertTrue(le.isDefault())
        self.assertTrue(le.isValid())
        self.assertEqual(le._choose_color(), "#AADDAA")

    def test_both_same(self):
        """Tests the logic when the value is valid and the default.
        """
        from dat.gui.generic import AdvancedLineEdit
        le = AdvancedLineEdit("test",
                              default="a",
                              validate=lambda t: t == "a")
        self._app.processEvents()
        self.assertEqual(le.text(), "test")
        self.assertFalse(le.isDefault())
        self.assertFalse(le.isValid())
        self.assertEqual(le._choose_color(), "#DDAAAA")

        le.setText("a")
        self._app.processEvents()
        self.assertTrue(le.isDefault())
        self.assertTrue(le.isValid())
        self.assertEqual(le._choose_color(), "#AAAADD")

    def test_follow(self):
        """Tests changing the default value when FOLLOW_DEFAULT_UPDATE is set.
        """
        from dat.gui.generic import AdvancedLineEdit
        le = AdvancedLineEdit("test",
                              default="a",
                              flags=AdvancedLineEdit.FOLLOW_DEFAULT_UPDATE)
        self._app.processEvents()
        self.assertFalse(le.isDefault())

        le.setDefault("b")
        self._app.processEvents()
        self.assertFalse(le.isDefault())
        self.assertEqual(le.text(), "test")

        le.setText("b")
        self._app.processEvents()
        self.assertTrue(le.isDefault())

        le.setDefault("c")
        self._app.processEvents()
        self.assertEqual(le.text(), "c")
        self.assertTrue(le.isDefault())

        le.setDefault("c")
        self._app.processEvents()
        self.assertTrue(le.isDefault())
