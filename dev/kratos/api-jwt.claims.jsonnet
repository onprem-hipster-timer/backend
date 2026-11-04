// Claims for the JWT the backend accepts (session to JWT, template "api"). Kratos already sets iss,
// sub (identity ID), sid, iat, nbf, exp and jti. The backend reads email, email_verified and name.
local session = std.extVar('session');
local traits = session.identity.traits;
local addresses = if 'verifiable_addresses' in session.identity then session.identity.verifiable_addresses else [];
local verified = [
  a
  for a in addresses
  if a.via == 'email' && a.verified && std.asciiLower(a.value) == std.asciiLower(traits.email)
];

{
  claims: {
    aud: 'http://localhost:2614',
    email: traits.email,
    email_verified: std.length(verified) > 0,
    [if 'name' in traits then 'name' else null]: traits.name,
  },
}
