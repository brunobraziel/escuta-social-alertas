import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("whatsapp_manage", Path(__file__).parents[1] / "infra/whatsapp/manage.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class WhatsAppDestinationTests(unittest.TestCase):
    def test_group_with_trailing_space_requires_correct_community(self):
        replies = ['[{"id":"123@g.us","subject":"Alerta de tendencias "}]',
                   '{"linkedParent":"456@g.us"}',
                   '{"subject":"Operativo do CP Lula - Tecnologia"}']
        with patch.object(manage, "request", side_effect=replies), patch.object(manage, "Path") as path, patch(
            "sys.argv", ["manage", "select-group", "--name", "Alerta de tendencias", "--community", "Operativo do CP Lula - Tecnologia"]):
            manage.main()
        path.return_value.write_text.assert_called_once_with("123@g.us")

    def test_wrong_community_never_changes_destination(self):
        replies = ['[{"id":"123@g.us","subject":"Alerta de tendencias"}]',
                   '{"linkedParent":"456@g.us"}', '{"subject":"Other community"}']
        with patch.object(manage, "request", side_effect=replies), patch.object(manage, "Path") as path, patch(
            "sys.argv", ["manage", "select-group", "--name", "Alerta de tendencias", "--community", "Operativo do CP Lula - Tecnologia"]):
            with self.assertRaises(SystemExit):
                manage.main()
        path.assert_not_called()

    def test_same_name_in_multiple_communities_selects_only_authorized_parent(self):
        replies = ['[{"id":"123@g.us","subject":"Alerta de tendencias"},{"id":"124@g.us","subject":"Alerta de tendencias"}]',
                   '{"linkedParent":"456@g.us"}', '{"subject":"Other community"}',
                   '{"linkedParent":"457@g.us"}', '{"subject":"Operativo do CP Lula - Tecnologia"}']
        with patch.object(manage, "request", side_effect=replies), patch.object(manage, "Path") as path, patch(
            "sys.argv", ["manage", "select-group", "--name", "Alerta de tendencias", "--community", "Operativo do CP Lula - Tecnologia"]):
            manage.main()
        path.return_value.write_text.assert_called_once_with("124@g.us")
