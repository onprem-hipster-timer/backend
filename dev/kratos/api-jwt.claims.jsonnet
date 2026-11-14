// Claims for the JWT the backend accepts (session to JWT, template "api"). Kratos already sets iss,
// sub (identity ID), sid, iat, nbf, exp and jti. The backend reads schema_id, email, email_verified and name.
// schema_id tells guests apart; with GUEST_ENABLED=true the backend refuses tokens without it.
// Guest identities have no email trait, so email is only added when the trait exists.
local session = std.extVar('session');
local identity = session.identity;
local traits = identity.traits;
local email = if 'email' in traits then traits.email else null;
local addresses = if 'verifiable_addresses' in identity then identity.verifiable_addresses else [];
local verified = [
  a
  for a in addresses
  if a.via == 'email' && a.verified && email != null && std.asciiLower(a.value) == std.asciiLower(email)
];

{
  claims: {
    aud: 'http://localhost:2614',
    schema_id: identity.schema_id,
    [if email != null then 'email' else null]: email,
    email_verified: std.length(verified) > 0,
    [if 'name' in traits then 'name' else null]: traits.name,
  },
}
