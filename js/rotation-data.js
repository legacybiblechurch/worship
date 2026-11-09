// Legacy Bible Church · the Sunday rotation
// Strict JSON between the braces: rotation.html edits it, scripts/rotation_now.py reads it.
//   people   the order. Slides goes down the list one Sunday each; Table runs the same
//            list tableOffset places behind, so nobody has both jobs the same week.
//   start    the Sunday people[0] has Slides and people[tableOffset] has Table.
//   changes  one Sunday done differently: {"slides": "Cole"}, {"table": "Joel"},
//            {"off": true, "note": "No service"}. Set from the page.
window.LBC_ROTATION = {
  "people": ["Quaid", "Cole", "Marco", "Michael", "Joel"],
  "start": "2026-11-15",
  "tableOffset": 2,
  "guide": "https://drive.google.com/drive/folders/1c20gNrB0OHoh_AZVM74sEqZhTE2I2h67",
  "changes": {}
};
