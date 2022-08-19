deleting
========

the system is not designed for deletions but they can be performed in special
cases.

usually a deletion should only be done if there's a security concern.

1. lock merges during the process (this can be done with branch protection)
1. remove the package from the `packages.ini` metadata (prevent reintroduction)
1. edit the `packages.json` to remove the deleted files:

   ```bash
   gsutil cp gs://pypi.devinfra.sentry.io/packages.json .
   cp packages.json{,.bak}
   "${EDITOR:-vim}" packages.json
   git diff --no-index packages.json{.bak,}
   gsutil -h 'Cache-Control: no store' cp packages.json gs://pypi.devinfra.sentry.io
   ```

1. (if removing the whole package) delete the index page for the package:

   ```bash
   gsutil ls gs://pypi.devinfra.sentry.io/simple/uwsgi-dogstatsd-plugin
   gsutil rm -r gs://pypi.devinfra.sentry.io/simple/uwsgi-dogstatsd-plugin
   ```

1. (if removing a version of a package) edit the index page for the package:

   ```bash
   gsutil cp gs://pypi.devinfra.sentry.io/simple/uwsgi-dogstatsd-plugin/index.html .
   cp index.html{,.bak}
   "${EDITOR:-vim}" index.html
   gsutil -h 'Cache-Control: public, max-age=300' cp index.html gs://pypi.devinfra.sentry.io/simple/uwsgi-dogstatsd-plugin/index.html
   ```

1. delete the wheels for the package:

   ```bash
   gsutil ls gs://pypi.devinfra.sentry.io/wheels/uwsgi_dogstatsd_plugin*
   gsutil rm gs://pypi.devinfra.sentry.io/wheels/uwsgi_dogstatsd_plugin*
   ```

1. unlock merges

_note that the index page may still link to the deleted package_ -- this is
harmless and will be cleaned up on the next execution
