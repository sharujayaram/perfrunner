from keywords.MobileRestClient import MobileRestClient

sg_client = MobileRestClient()
sg_client.create_user("http://172.23.100.204:4985", "db", "autotest", password="password", channels=["ABC"])