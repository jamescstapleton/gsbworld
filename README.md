# GSB World

A small 3D game set on the Stanford GSB (Knight Management Center) campus. You
walk around as a little Christmas tree, chat with the people on Town Square,
and sit at the café tables under the Arbuckle pergola while people stop by to
talk. The conversations are the class's blast emails.

The campus is a low-poly model built in Blender from the GSB directory map,
textured from photos of the buildings, and played in the browser with
[Three.js](https://threejs.org/).

## Play

**Play online: <https://jamescstapleton.github.io/gsbworld/>**

Every push to `main` republishes the game through GitHub Pages
(`.github/workflows/pages.yml`).

To run it locally instead: the game is in `web/`. Browsers won't load the 3D
model straight from disk, so serve the folder with any local web server:

```bash
cd web
python -m http.server 8000
```

Then open <http://localhost:8000>.

| Key | Action |
| --- | --- |
| WASD | Walk |
| Arrow keys | Walk 3× faster |
| Shift | Run (doubles either speed) |
| Space | Talk to someone nearby, or sit down at an empty table |
| Space again | Leave the chat |
| Drag / scroll | Look around / zoom |

While sitting, visitors come by one at a time; press any movement key to stand up.

## How it's built

| File | What it does |
| --- | --- |
| `gsb_campus.py` | Blender script: buildings, roofs, pergola, furniture, trees, sky and sun. Run it in Blender's Scripting tab. Set `EXPORT_GLB = "web/gsb_campus.glb"` to export the model for the game. |
| `make_textures.py` | Cuts the facade, roof and stucco textures in `textures/` out of the building photos. |
| `overlay_check.py` | Draws the traced building footprints over the directory map, to check the tracing. |
| `make_dialogue.py` | Turns the blast-email CSV into `web/emails.json`, masking addresses, phone numbers and links, replacing names with initials and moving sender addresses to `example.edu`. |
| `web/main.js` | Scene, lighting (a sun plus a shader that darkens the campus by distance from Town Square), model loading. |
| `web/player.js` | The walking tree, controls and follow camera. |
| `web/people.js` | The crowd: walkers on a path network around Town Square and people seated at the tables. |
| `web/chat.js` | Talk prompts, the over-the-shoulder chat camera and the email-style chat bubble. |
| `web/seating.js` | Sitting at tables and the visitor loop. |

The source photos, the directory map and the `.blend` file aren't in the
repository; you need them only to rebuild the textures or the model.

### Updating the emails

```bash
python make_dialogue.py gsb_blast_emails.csv web/emails.json
```

Names are replaced with initials when they're listed in `private_names.txt`
(one per line), kept next to the CSV. That file and the raw CSV hold real names,
so `.gitignore` keeps both out of the repository.
