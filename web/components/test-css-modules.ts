// Static markup tests exercise component content and behavior. Styles are
// compiled by the production build and inspected in the browser.
import { createRequire } from "node:module";

const testRequire = createRequire(`${process.cwd()}/package.json`);
testRequire.extensions[".css"] = (loadedModule) => {
  loadedModule.exports = { theme: "theme" };
};
