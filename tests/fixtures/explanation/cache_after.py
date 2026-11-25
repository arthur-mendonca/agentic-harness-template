class ProfileService:
    def __init__(self, store):
        self.store = store
        self._cache = {}

    def read_profile(self, tenant_id, user_id):
        key = (tenant_id, user_id)
        if key not in self._cache:
            self._cache[key] = self.store.fetch_profile(tenant_id, user_id)
        return dict(self._cache[key])

    def update_profile(self, tenant_id, user_id, values):
        self.store.update_profile(tenant_id, user_id, values)
        self._cache.pop((tenant_id, user_id), None)
