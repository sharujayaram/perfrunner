
from CBL.SyncGatewayHelper import SGHelper
from CBL.Database import Database

cbl_db_name = "cbl_db3"
cbl_url = "http://10.17.2.156:8080"
replicator_authenticator_type = "session"
sg_url = "http://172.23.100.204:4985"
sg_db_name = "db"
sg_blip_url = "ws://172.23.100.204:4984/{}".format(sg_db_name)
channels = ["ABC"]
replication_type = "push"




db = Database(cbl_url)
db_config = db.configure() #def configure(self, directory=None, conflictResolver=None, password=None):
cbl_db = db.create(cbl_db_name, db_config)
#db.create_bulk_docs(number=10000, id_prefix="poc3", db=cbl_db, channels=channels)
#cbl_added_doc_ids = db.getDocIds(cbl_db)
#print("Added docs to CBL: {}".format(cbl_added_doc_ids))

'''
sync_gateway = SGHelper()
sync_gateway.create_user(sg_url, sg_db_name, "autotest", password="password", channels=["ABC"])
cookie, session = sync_gateway.create_session("http://172.23.100.204:4985", "db", "autotest", "password")
auth_session = cookie, session
sync_cookie = "{}={}".format(cookie, session)
session_header = {"Cookie": sync_cookie}
'''