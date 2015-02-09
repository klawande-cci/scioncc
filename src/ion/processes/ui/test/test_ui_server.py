#!/usr/bin/env python

__author__ = 'Michael Meisiger'

from nose.plugins.attrib import attr
import requests

from pyon.util.int_test import IonIntegrationTestCase

from pyon.public import PRED, RT, BadRequest, NotFound, CFG

from interface.services.core.iidentity_management_service import IdentityManagementServiceClient
from interface.services.core.iorg_management_service import OrgManagementServiceClient
from interface.services.core.iresource_registry_service import ResourceRegistryServiceClient

from interface.objects import Org, UserRole, ActorIdentity, UserIdentityDetails


@attr('INT', group='coi')
class TestUIServer(IonIntegrationTestCase):

    def setUp(self):
        self._start_container()
        self.container.start_rel_from_url('res/deploy/basic.yml')

        self.resource_registry = ResourceRegistryServiceClient()
        self.org_client = OrgManagementServiceClient()
        self.idm_client = IdentityManagementServiceClient()

        self.ui_server_proc = self.container.proc_manager.procs_by_name["ui_server"]
        port = self.ui_server_proc.server_port
        sg_prefix = self.ui_server_proc.service_gateway.url_prefix
        self.ui_base_url = "http://localhost:%s" % (port, )
        self.sg_base_url = self.ui_base_url + sg_prefix

    def test_ui_server(self):
        actor_identity_obj = ActorIdentity(name="John Doe")
        actor_id = self.idm_client.create_actor_identity(actor_identity_obj)
        self.idm_client.set_actor_credentials(actor_id, "jdoe", "mypasswd")

        actor_details = UserIdentityDetails()
        actor_details.contact.individual_names_given = "John"
        actor_details.contact.individual_name_family = "Doe"
        self.idm_client.define_identity_details(actor_id, actor_details)

        # TEST: Authentication
        self._do_test_authentication()

        # TEST: Service gateway
        self._do_test_service_gateway(actor_id)

        self.idm_client.delete_actor_identity(actor_id)

    def _do_test_authentication(self):
        session = requests.session()

        # TEST: Login
        resp = session.get(self.ui_base_url + "/auth/session")
        resp_json = self._assert_json_response(resp, None)
        self.assertEquals("", resp_json["result"]["username"])

        resp = session.get(self.ui_base_url + "/auth/login?username=jdoe&password=foo")
        self._assert_json_response(resp, None, status=404)

        resp = session.get(self.ui_base_url + "/auth/session")
        resp_json = self._assert_json_response(resp, None)
        self.assertEquals("", resp_json["result"]["username"])

        resp = session.get(self.ui_base_url + "/auth/login?username=jdoe&password=mypasswd")
        resp_json = self._assert_json_response(resp, None)
        self.assertIn("actor_id", resp_json["result"])
        self.assertIn("username", resp_json["result"])
        self.assertIn("full_name", resp_json["result"])
        self.assertEquals("jdoe", resp_json["result"]["username"])

        resp = session.get(self.ui_base_url + "/auth/session")
        resp_json = self._assert_json_response(resp, None)
        self.assertEquals("jdoe", resp_json["result"]["username"])

        resp = session.get(self.ui_base_url + "/auth/logout")
        self._assert_json_response(resp, "OK")

        resp = session.get(self.ui_base_url + "/auth/session")
        resp_json = self._assert_json_response(resp, None)
        self.assertEquals("", resp_json["result"]["username"])

    def _do_test_service_gateway(self, actor_id):
        # We don't want to modify import order during testing, so import here
        from ion.services.service_gateway import SG_IDENTIFICATION

        session = requests.session()

        # TEST: Service gateway available
        resp = session.get(self.sg_base_url + "/")
        self._assert_json_response(resp, SG_IDENTIFICATION)

        # TEST: Login
        resp = session.get(self.ui_base_url + "/auth/login?username=jdoe&password=mypasswd")
        resp_json = self._assert_json_response(resp, None)
        self.assertEquals("jdoe", resp_json["result"]["username"])

        # TEST: Service access
        resp = session.get(self.sg_base_url + "/request/resource_registry/find_resources?restype=ActorIdentity&id_only=True")
        resp_json = self._assert_json_response(resp, None)
        self.assertIn(actor_id, resp_json["result"][0])

    def _assert_json_response(self, resp, result, status=200):
        self.assertIn("application/json", resp.headers["content-type"])
        if status:
            self.assertEquals(status, resp.status_code)
        resp_json = resp.json()
        if result is not None:
            self.assertIn("result", resp_json)
            if type(result) in (str, unicode, int, long, float, bool):
                self.assertEquals(result, resp_json["result"])
            else:
                self.fail("Unsupported result type")
        return resp_json