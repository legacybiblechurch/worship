// Legacy Bible Church · the Sunday rotation
// Strict JSON between the braces: rotation.html edits it, scripts/rotation_now.py reads it.
//   people   the order. Each job walks down the list one Sunday at a time.
//   jobs     each job's offset into the list. Different offsets mean nobody has
//            two jobs the same Sunday. With five people and 0, 1, 3 a person has
//            Slides, two weeks later Table, two weeks later Stream, then round again.
//   start    the Sunday people[0] has Slides.
//   changes  one Sunday done differently: {"slides": "Cole"}, {"stream": "Joel"},
//            {"off": true, "note": "No service"}. Set from the page.
window.LBC_ROTATION = {
  "people": ["Quaid", "Cole", "Marco", "Michael", "Joel"],
  "jobs": {"slides": 0, "stream": 1, "table": 3},
  "start": "2026-11-15",
  "guide": "https://drive.google.com/drive/folders/1c20gNrB0OHoh_AZVM74sEqZhTE2I2h67",
  "changes": {}
};
