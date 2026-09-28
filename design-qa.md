# Business Type Selector QA - 2026-09-28

## Follow-up: Compact Workbench And Collapsible Preview

The later layout uses a 400px sidebar (360px in smaller split views) and an 840x740 default window. Quantity and business type are inline; the selected-type trigger fits its text while the existing two-column popover stays unchanged. Both the preview header and sidebar expose text-labelled SVG collapse controls. Native collapse requests 400px width, restores the previous expanded width on reopen, and preserves the current height using logical pixels. Maximized windows first leave maximized mode. No settings or business-flow changes.

Verification: production build/type checking passed. Isolated Playwright checks cover 14 options, compact/expanded layouts, preserved long and extra fields, scroll access, 150% DPI window-command conversion, 700/380px viewports, settings in compact mode, theme, resize rejection and the existing 30-second hide-content timer followed by restoring the last data. Screenshots inspected: ../Temp/preview-expanded.png, ../Temp/preview-collapsed.png, ../Temp/preview-dark.png. The collapsed layout no longer leaves a separator above unused space or wraps the log heading.

Window commands were mocked; actual Windows/WebView2 resizing was not exercised. Business actions were forbidden by the test harness. Earlier binary hashes below describe the previous selector-only build, not this follow-up.

Desktop release build passed; dist_green/ApprovalTool.exe replaced and SHA256 matched the build: `13DDC738E83AE769E2B96FDA8FB13AAC6366A42823AA97D132E92F45A87DB490`. Python runner retained the department fix (`2793BCC213D29E868C8471C3A50754825893CBB697A9E007C90126E26BEFA93E`). No configuration files were replaced.

Sharing distribution regenerated from this build: 629 runtime files match dist_green; first-run push settings are disabled with blank credentials/directory. Scan found no known personal push credentials, logs, SQLite state, workflow settings or browser profile. Updated guides and command entry are included. These local portable distributions are separate from the source Git repository; a Git push does not create a downloadable GitHub Release.

final result: passed

## Scope And Evidence

Selected target: first displayed concept, "双列浮层" (exec-1d51784c-b536-4888-8844-788ecd6280e0.png).
Implementation: BusinessTypeSelect.vue, integrated into the existing LeftPanel.
Screenshot: ../Temp/business-type-final.png, 920 x 740, light theme, selector open.
Both images were inspected together; the generated reference is higher resolution with the same aspect ratio.
The target is the selector, not a replacement of unrelated application sections.

## Findings

No outstanding P0/P1/P2 issues in the scoped control.
Intentional differences: preserve existing application typography and approval-button placement; omit the concept caption and duplicated bottom approval buttons present in the generated mock.

## Fidelity

- Typography: readable 13px option labels at actual desktop size, full long names, matching existing product fonts.
- Layout: anchored two-column/seven-row floating list with header and 14-item count; opening leaves the approval-button rectangle unchanged.
- Color: existing warm light and dark tokens, amber selection, visible keyboard focus, subtle border/shadow.
- Assets: no new raster artwork; existing icon stroke language for check and chevron, original page artwork untouched.
- Content: all 14 original labels/order retained from incoming options, no new hard-coded business categories in production code.

## Interaction Verification

In-app browser with synthetic configuration only; no actual approval or registration.
Mouse selection closes and displays the selected value. Enter opens/confirms; Space opens; Home/End and arrows move focus; Escape retains the prior value; Tab and outside click close.
Checked 920x740, 700x600, 390x700 light/dark, and 700x400 short viewport.
Narrow list has no horizontal overflow; short-window final option remains reachable by End and selectable.
Browser error/warning log empty. Frontend type-check and production build passed.

Native Windows WebView2 rendering was not separately exercised; green executable uses the same built frontend.

Release build passed and dist_green/ApprovalTool.exe was replaced. Build/deployed SHA256 match:
F5B1A23E876409A273BDD0FB7D455D8AD4EC3CBEC8B68B45C9CBE442D87C52E4.
Only the main executable was replaced; local settings and the Python runner were not changed.
