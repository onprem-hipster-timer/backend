// Body of the login web_hook (selfservice.flows.login.after.password) when guests are on.
// Members with a verified address never reach the backend ('cancel' skips the web_hook), so their login
// does not depend on it. The backend allows a guest only while its guest row exists and its resource
// accepts it, and refuses members without a verified address.
// 'guest' must equal the backend's KRATOS_GUEST_SCHEMA_ID.
function(ctx)
  local identity = ctx.identity;
  local addresses = if 'verifiable_addresses' in identity then identity.verifiable_addresses else [];
  local verified = std.length([a for a in addresses if a.verified]) > 0;
  if identity.schema_id != 'guest' && verified then error 'cancel' else {
    identity_id: identity.id,
    schema_id: identity.schema_id,
    verified: verified,
  }
