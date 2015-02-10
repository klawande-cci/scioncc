#!/usr/bin/env python

__author__ = 'Thomas R. Lennan, Stephen Henrie, Michael Meisinger'

from uuid import uuid4
import bcrypt

#from pyon.core.security.authentication import Authentication
from pyon.public import log, RT, OT, Inconsistent, NotFound, BadRequest, get_ion_ts_millis, Unauthorized

from interface.objects import SecurityToken, TokenTypeEnum, Credentials

from interface.services.core.iidentity_management_service import BaseIdentityManagementService

MAX_TOKEN_VALIDITY = 365*24*60*60


class IdentityManagementService(BaseIdentityManagementService):
    """
    Stores identities of users and resources, including bindings of internal
    identities to external identities. Also stores metadata such as a user profile.
    """

    def on_init(self):
        self.rr = self.clients.resource_registry
        #self.authentication = Authentication()

    def create_actor_identity(self, actor_identity=None):
        self._validate_resource_obj("actor_identity", actor_identity, RT.ActorIdentity, checks="noid,name")
        if actor_identity.credentials:
            raise BadRequest("Cannot create actor with credentials")
        if actor_identity.details and actor_identity.details.type_ == OT.IdentityDetails:
            actor_identity.details = None

        actor_id, _ = self.rr.create(actor_identity)

        return actor_id

    def update_actor_identity(self, actor_identity=None):
        old_actor = self._validate_resource_obj("actor_identity", actor_identity, RT.ActorIdentity, checks="id,name")

        # Prevent security risk because contained credentials may be manipulated
        actor_identity.credentials = old_actor.credentials

        self.rr.update(actor_identity)

    def read_actor_identity(self, actor_id=''):
        actor_obj = self._validate_resource_id("actor_id", actor_id, RT.ActorIdentity)

        return actor_obj

    def delete_actor_identity(self, actor_id=''):
        self._validate_resource_id("actor_id", actor_id, RT.ActorIdentity)

        self.rr.delete(actor_id)

    def find_actor_identity_by_name(self, name=''):
        """Return the ActorIdentity object whose name attribute matches the passed value.
        """
        objects, _ = self.rr.find_resources(RT.ActorIdentity, None, name, id_only=False)
        if not objects:
            raise NotFound("ActorIdentity with name %s does not exist" % name)
        if len(objects) > 1:
            raise Inconsistent("Multiple ActorIdentity objects with name %s exist" % name)
        return objects[0]

    # -------------------------------------------------------------------------
    # Credentials handling

    def register_credentials(self, actor_id='', credentials=None):
        actor_obj = self._validate_resource_id("actor_id", actor_id, RT.ActorIdentity)
        self._validate_arg_obj("credentials", credentials, OT.Credentials)

        actor_obj.credentials.append(credentials)

        if credentials.username:
            actor_obj.alt_ids.append("UNAME:" + credentials.username)

        # Lower level RR call to avoid credentials clearing
        self.rr.update(actor_obj)

    def unregister_credentials(self, actor_id='', credentials_name=''):
        actor_obj = self._validate_resource_id("actor_id", actor_id, RT.ActorIdentity)
        if not credentials_name:
            raise BadRequest("Invalid credentials_name")
        found_cred = -1
        for i, cred in enumerate(actor_obj.credentials):
            if cred.username == credentials_name:
                found_cred = i
                break
        if found_cred != -1:
            del actor_obj.credentials[found_cred]
        else:
            raise NotFound("Credentials not found")

        actor_obj.alt_ids.remove("UNAME:" + credentials_name)

        # Lower level RR call to avoid credentials clearing
        self.rr.update(actor_obj)

    def find_actor_identity_by_username(self, username=''):
        if not username:
            raise BadRequest("Invalid username")
        res_ids, _ = self.rr.find_resources_ext(alt_id_ns="UNAME", alt_id=username, id_only=True)
        if not res_ids:
            raise NotFound("No actor found with username")
        return res_ids[0]

    def set_actor_credentials(self, actor_id='', username='', password=''):
        if not username:
            raise BadRequest("Invalid username")
        self._check_pwd_policy(password)
        actor_obj = self._validate_resource_id("actor_id", actor_id, RT.ActorIdentity)
        cred_obj = None
        for cred in actor_obj.credentials:
            if cred.username == username:
                cred_obj = cred
                break
        if not cred_obj:
            cred_obj = Credentials()
            cred_obj.username = username
            actor_obj.credentials.append(cred_obj)
            actor_obj.alt_ids.append("UNAME:" + username)

        self._generate_password_hash(cred_obj, password)

        # Lower level RR call to avoid credentials clearing
        self.rr.update(actor_obj)

    def set_user_password(self, username='', password=''):
        if not username:
            raise BadRequest("Invalid username")
        self._check_pwd_policy(password)
        actor_id = self.find_actor_identity_by_username(username)
        actor_obj = self.read_actor_identity(actor_id)

        cred_obj = None
        for cred in actor_obj.credentials:
            if cred.username == username:
                cred_obj = cred
                break

        self._generate_password_hash(cred_obj, password)

        # Lower level RR call to avoid credentials clearing
        self.rr.update(actor_obj)

    def _generate_password_hash(self, cred_obj, password):
        if not cred_obj or cred_obj.type_ != OT.Credentials:
            raise BadRequest("Invalid cred_obj")
        cred_obj.identity_provider = "AgProX"
        cred_obj.authentication_service = "AgProX IdM"
        cred_obj.password_salt = bcrypt.gensalt()
        cred_obj.password_hash = bcrypt.hashpw(password, cred_obj.password_salt)

    def check_actor_credentials(self, username='', password=''):
        if not username:
            raise BadRequest("Invalid argument username")
        if not password:
            raise BadRequest("Invalid argument password")

        actor_id = self.find_actor_identity_by_username(username)
        actor_obj = self.read_actor_identity(actor_id)

        cred_obj = None
        for cred in actor_obj.credentials:
            if cred.username == username:
                cred_obj = cred
                break

        if bcrypt.hashpw(password, cred_obj.password_salt) != cred_obj.password_hash:
            raise NotFound("Invalid password")

        return actor_obj._id

    def _check_pwd_policy(self, password):
        if not password or type(password) is not str:
            raise BadRequest("Invalid type")
        if len(password) < 3:
            raise BadRequest("Password too short")

    # -------------------------------------------------------------------------
    # Identity details (user profile) handling

    def define_identity_details(self, actor_id='', identity_details=None):
        actor_obj = self._validate_resource_id("actor_id", actor_id, RT.ActorIdentity)
        if not identity_details:
            raise BadRequest("Invalid argument identity_details")
        if actor_obj.details:
            if actor_obj.details.type_ != identity_details.type_:
                raise BadRequest("Type for identity_details does not match")
        actor_obj.details = identity_details

        self.update_actor_identity(actor_obj)

    def read_identity_details(self, actor_id=''):
        actor_obj = self.read_actor_identity(actor_id)

        return actor_obj.details


    # -------------------------------------------------------------------------
    # Manage authentication tokens
    # TODO: More compliant with OAuth2

    def _generate_auth_token(self, actor_id=None, expires=""):
        token_string = uuid4().hex
        token = SecurityToken(token_type=TokenTypeEnum.ACTOR_AUTH, token_string=token_string,
                              actor_id=actor_id, expires=expires, status="OPEN")
        return token

    def create_authentication_token(self, actor_id='', start_time='', validity=0):
        """Create an authentication token for provided actor id with a given start time and validity.
        start_time defaults to current time if empty and uses a system timestamp.
        validity is in seconds and must be set.
        """
        if not actor_id:
            raise BadRequest("Must provide argument: actor_id")
        actor_obj = self.rr.read(actor_id)
        if actor_obj.type_ != RT.ActorIdentity:
            raise BadRequest("Illegal type for argument actor_id")
        if type(validity) not in (int, long):
            raise BadRequest("Illegal type for argument validity")
        if validity <= 0 or validity > MAX_TOKEN_VALIDITY:
            raise BadRequest("Illegal value for argument validity")
        cur_time = get_ion_ts_millis()
        if not start_time:
            start_time = cur_time
        start_time = int(start_time)
        if start_time > cur_time:
            raise BadRequest("Illegal value for start_time: Future values not allowed")
        if (start_time + 1000*validity) < cur_time:
            raise BadRequest("Illegal value for start_time: Already expired")
        expires = str(start_time + 1000*validity)

        token = self._generate_auth_token(actor_id, expires=expires)
        token_id = "token_%s" % token.token_string

        self.container.object_store.create(token, token_id)

        return token.token_string

    def read_authentication_token(self, token_string=''):
        """Returns the token object for given actor authentication token string.
        """
        token_id = "token_%s" % token_string
        token = self.container.object_store.read(token_id)
        if not isinstance(token, SecurityToken):
            raise Inconsistent("Token illegal type")
        return token

    def update_authentication_token(self, token=None):
        """Updates the given token.
        """
        if not isinstance(token, SecurityToken):
            raise BadRequest("Illegal argument type: token")
        if token.token_type != TokenTypeEnum.ACTOR_AUTH:
            raise BadRequest("Argument token: Illegal type")
        cur_time = get_ion_ts_millis()
        token_exp = int(token.expires)
        if token_exp > cur_time + 1000*MAX_TOKEN_VALIDITY:
            raise BadRequest("Argument token: Maximum expiry extended")

        self.container.object_store.update(token)

    def invalidate_authentication_token(self, token_string=''):
        """Invalidates an authentication token, but leaves it in place for auditing purposes.
        """
        token_id = "token_%s" % token_string
        token = self.container.object_store.read(token_id)
        if not isinstance(token, SecurityToken):
            raise Inconsistent("Token illegal type")
        if token.token_type != TokenTypeEnum.ACTOR_AUTH:
            raise BadRequest("Illegal token type")
        token.status = "INVALID"
        self.container.object_store.update(token)
        log.info("Invalidated security auth token: %s", token.token_string)

    def check_authentication_token(self, token_string=''):
        """Checks given token and returns a dict with actor id if valid.
        """
        token_id = "token_%s" % token_string
        token = self.container.object_store.read(token_id)
        if not isinstance(token, SecurityToken):
            raise Inconsistent("Token illegal type")
        if token.token_type != TokenTypeEnum.ACTOR_AUTH:
            raise BadRequest("Illegal token type")
        if token.token_string != token_string:
            raise Inconsistent("Found token's token_string does not match")
        cur_time = get_ion_ts_millis()
        if token.status != "OPEN":
            raise Unauthorized("Token status invalid")
        if cur_time >= int(token.expires):
            raise Unauthorized("Token expired")

        token_info = dict(actor_id=token.actor_id,
                    expiry=token.expires,
                    token=token,
                    token_id=token_id)

        log.info("Authentication token %s resolved to actor %s, expiry %s", token_string, token.actor_id, token.expires)

        return token_info

    def _get_actor_authentication_tokens(self, actor_id):
        actor_tokens = []
        raise NotImplementedError("TODO")
        return actor_tokens
