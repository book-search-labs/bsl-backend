INSERT INTO user_account (
  email,
  password_hash,
  name,
  phone,
  email_verified,
  status,
  deleted_at
)
VALUES (
  'demo@bslbooks.local',
  'sha256:84ba3f18dee9df85e158328f14b7b69003a0f979ae63002a282be60d585edb8d',
  'BSL 회원',
  '010-0000-0000',
  1,
  'ACTIVE',
  NULL
)
ON DUPLICATE KEY UPDATE
  password_hash = VALUES(password_hash),
  name = VALUES(name),
  phone = VALUES(phone),
  email_verified = VALUES(email_verified),
  status = 'ACTIVE',
  deleted_at = NULL;
