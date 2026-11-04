// Google -> identity traits. Only a Google-verified email becomes the identifier and is marked
// verified; name is optional.
local claims = {
  email_verified: false,
} + std.extVar('claims');

{
  identity: {
    traits: {
      [if 'email' in claims && claims.email_verified then 'email' else null]: claims.email,
      [if 'name' in claims && claims.name != '' then 'name' else null]: claims.name,
    },
    verified_addresses: std.prune([
      if 'email' in claims && claims.email_verified then { via: 'email', value: claims.email },
    ]),
  },
}
