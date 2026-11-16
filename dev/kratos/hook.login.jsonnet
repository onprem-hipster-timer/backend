// Body of the guest login web_hook (selfservice.flows.login.after.password, before require_verified_address)
// when guests are on. Only guests reach the backend ('cancel' skips the web_hook for every other schema), so
// member login is decided by require_verified_address alone. The backend allows a guest only while its guest
// row exists and its resource accepts it.
// 'guest' must equal the backend's KRATOS_GUEST_SCHEMA_ID.
function(ctx)
  if ctx.identity.schema_id != 'guest' then error 'cancel' else {
    identity_id: ctx.identity.id,
    schema_id: ctx.identity.schema_id,
  }
