// Body of the settings web_hooks (selfservice.flows.settings.after.profile|password|oidc) when guests are on.
// Only guests reach the backend ('cancel' skips the web_hook for every other schema). ctx.identity holds
// the changed identity before Kratos stores it; the backend allows only a name change.
// 'guest' must equal the backend's KRATOS_GUEST_SCHEMA_ID.
function(ctx)
  if ctx.identity.schema_id != 'guest' then error 'cancel' else {
    identity_id: ctx.identity.id,
    schema_id: ctx.identity.schema_id,
    traits: ctx.identity.traits,
  }
