# Real-environment fixtures

Minimal, synthetic stand-ins for five real MWAA environments the scan got wrong,
reduced to the lines that decide "is this configured?" (names, buckets, secret
ids and account details are all placeholders -- this repo is public). Each
directory is one environment:

- `environment.json` -- the GetEnvironment fields that matter. An
  `...S3ObjectVersion` of `"<latest>"` means "configured at the object's latest
  version", i.e. no unapplied upload.
- `objects.json` -- S3 key -> fixture file holding its content, for every
  object that exists. Keys not listed don't exist.
- the content files themselves.

`configured-281` isn't one of the five: it's probe-281 with the transport and the
stale constraints pin fixed, the reference for what a correctly configured flagged
environment looks like.

`test_real_environments.py` loads each into a `FakeS3Client` and asserts the
outcome the real environment should get. The site for all of them is datad0g.com.
