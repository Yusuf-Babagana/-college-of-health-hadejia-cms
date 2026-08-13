# static/vendor/

This directory exists **only** to intentionally shadow specific static
files shipped inside third-party packages (currently: jazzmin's default
"no avatar" stock photo at `vendor/adminlte/img/user2-160x160.jpg`).

Django's staticfiles `FileSystemFinder` (which serves `STATICFILES_DIRS`,
i.e. this `static/` folder) runs before `AppDirectoriesFinder` (which
serves each installed app's own `static/` folder), so any file placed
here at the *same relative path* as one shipped by a package wins,
without needing to touch `site-packages`.

This is deliberate and narrow - do **not** drop our own bundled
third-party libraries (Bootstrap, htmx, Alpine, etc.) in here, since an
arbitrary path here could accidentally collide with some other
package's own `vendor/` folder later. Those live in `static/lib/`
instead. Only add files here when the goal is specifically to override
one exact path from an installed package, and note which package/path
each override targets.

## Current overrides

- `vendor/adminlte/img/user2-160x160.jpg` - replaces jazzmin's stock
  default user-avatar photo (a stock photo of a man raising his index
  finger) with the college crest, shown for any admin/staff account that
  hasn't uploaded a profile picture.
