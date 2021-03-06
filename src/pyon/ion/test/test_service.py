#!/usr/bin/env python

__author__ = 'Adam R. Smith'

import uuid

from pyon.util.int_test import IonIntegrationTestCase

from pyon.core.bootstrap import IonObject
from pyon.core.exception import NotFound
from pyon.ion.resource import RT
from pyon.ion.service import BaseService
from pyon.util.containers import DotDict


class TestService(BaseService):
    name = 'test-service'
    clients = DotDict()


class ServiceTest(IonIntegrationTestCase):

    def setUp(self):
        self._start_container()
        self.rr = self.container.resource_registry

    def test_serve(self):
        srv = TestService()
        #srv.serve_forever()

    def test_validate_resource_id(self):
        srv = TestService()
        srv.clients.resource_registry = self.rr
        res_obj1 = IonObject(RT.ActorIdentity)

        newid = uuid.uuid4().hex
        rid1, _ = self.rr.create(res_obj1, object_id=newid)
        res_val_obj = srv._validate_resource_id("_id", rid1, optional=True)
        self.assertTrue(res_val_obj)
        self.assertRaises(NotFound, srv._validate_resource_id, arg_name="_id",
                          resource_id="badId",
                          optional=False)
        self.assertIsNone(srv._validate_resource_id("_id", "", optional=True))
        self.assertIsNone(srv._validate_resource_id("_id", None, optional=True))
        newid2 = uuid.uuid4().hex
        with self.assertRaises(NotFound):
            srv._validate_resource_id("_id", newid2, optional=True)
        self.rr.delete(rid1)
