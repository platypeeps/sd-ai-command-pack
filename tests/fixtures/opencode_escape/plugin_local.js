// An inert opencode 2.x server plugin (sd:2445). It registers and does
// nothing; a test drops it into a config dir's `plugins/` to see whether
// opencode loads it and whether the confinement probe refuses it.
export default { id: "sd-fixture-local", async setup() {} }
