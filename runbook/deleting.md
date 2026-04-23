deleting
========

the system is not designed for deletions but they can be performed in special
cases.

usually a deletion should only be done if there's a security concern.

1. lock merges during the process (this can be done with branch protection)
2. remove the package from the `packages.ini` metadata (prevent reintroduction)
3a. (if removing a version of a package) use the automated script:

   ```bash
   # preview what will change (dry run is the default)
   ./bin/delete-version <package> <version>

   # apply
   ./bin/delete-version <package> <version> --execute
   ```

   this updates `packages.json`, edits the package's `simple/` index page, and
   deletes the specific wheels and their `.metadata` sidecars.

3b. (if removing the whole package) perform the steps manually:

   ```bash
   # remove from packages.json
   gsutil cp gs://pypi.devinfra.sentry.io/packages.json .
   cp packages.json{,.bak}
   "${EDITOR:-vim}" packages.json
   git diff --no-index packages.json{.bak,}
   gsutil -h 'Cache-Control: no-store' cp packages.json gs://pypi.devinfra.sentry.io

   # delete the index page
   gsutil rm -r gs://pypi.devinfra.sentry.io/simple/uwsgi-dogstatsd-plugin

   # delete all wheels for the package
   gsutil ls gs://pypi.devinfra.sentry.io/wheels/uwsgi_dogstatsd_plugin*
   gsutil rm gs://pypi.devinfra.sentry.io/wheels/uwsgi_dogstatsd_plugin*
   ```

4. unlock merges

_note that the index page may still link to the deleted package_ -- this is
harmless and will be cleaned up on the next execution
