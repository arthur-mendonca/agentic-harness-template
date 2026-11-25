class ProfileService:
    def __init__(self, store):
        self.store = store

    def read_profile(self, tenant_id, user_id):
        return dict(self.store.fetch_profile(tenant_id, user_id))

    def update_profile(self, tenant_id, user_id, values):
        self.store.update_profile(tenant_id, user_id, values)
