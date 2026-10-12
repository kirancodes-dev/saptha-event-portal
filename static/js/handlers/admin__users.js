/* Handlers for the admin user pages (UPG-75), bound by static/js/handlers.js. */
Object.assign(window.SE_H = window.SE_H || {}, {
  'admin/users:confirm-delete': function () {
    return confirm('Delete this account? Their registrations stay, but they lose access. Deactivating is usually better.');
  },
});
