# Transferring templates to trial servers

Use the same application revision on development and trial servers. Run these
commands from the project root with the Python interpreter for that installation.
Django uses that server's configured database and media storage automatically.

On development, export the desired categories:

```sh
python manage.py transfer_templates export trial-templates.json --category Sponsors --category CraftMarket
```

Use the actual category values stored in your template editor; they may differ
from application names. Omit `--category` to export every category. All versions
are included, including expired and future templates and named attachment
sources. The export refuses to overwrite an existing bundle file.

Copy the resulting file to each trial server using your normal deployment or
file-transfer process. Then inspect the proposed import:

```sh
python manage.py transfer_templates import trial-templates.json --dry-run
python manage.py transfer_templates import trial-templates.json
```

The bundle contains template text, signature, subject, category, subcategory,
summary, Use from date and all attachment metadata. Uploaded attachment bytes
are embedded in the JSON; source database IDs and media paths are not imported.
Named attachments continue to resolve by category, subcategory and summary.
Uploaded files are saved through the destination's configured file storage.

An existing version is matched using category, subcategory, summary and Use from
date. Identical versions, including attachment contents, are skipped. Conflicts
abort the entire import before changes are made. If the trial version should be
replaced, explicitly use:

```sh
python manage.py transfer_templates import trial-templates.json --replace --dry-run
python manage.py transfer_templates import trial-templates.json --replace
```

Replacement updates that version and replaces its attachment rows. Other versions
and categories are retained. Old uploaded files are not deleted because another
record may reference them. Ambiguous versions with duplicate matching keys are
rejected; give such templates distinct summaries or dates before transferring.
Changing a summary/date creates a separate version rather than renaming an old one.

Only import bundles you trust: the contents are editable Django templates.
The command transfers no contributors, events, credentials or email settings.
HTML links, embedded image URLs, and hard-coded development URLs remain unchanged;
copy linked assets separately or use URLs accessible from the trial server.
For generated links, templates can use the existing `base_url` context variable.
Use from dates are preserved, so importing does not activate future templates.
No emails are sent during export or import.
