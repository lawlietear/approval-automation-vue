# Business Type Selector QA - 2026-09-28

## 2.3.2 Packaging Verification - 2026-09-30

Supersedes earlier not-packaged status: frontend and Windows release build passed; dist_green and dist_share now contain the same 2.3.2 EXE (SHA256 66076ae102c41ce8e109c1f4b5013de2b4ae9885e2b88537f2c1f30a27fc2500). All 629 runtime files match. Recorded personal configuration hashes remain unchanged; share scan found no known push credentials. Both ZIPs passed CRC and content checks; update signature verified and tampered data rejected. Only a draft manifest was generated; nothing uploaded and no real office upgrade executed.

## Regular Selector Clarification - 2026-09-30

Latest requirement supersedes the all-visible regular layout below: only 金融不良资产 / 存量资产处置 / 非金不良资产 stay as chips. The other seven regular types use the existing two-column dropdown, without duplicating shortcuts. OA remains flat. Tests verify placeholder reset, mutually exclusive selection, dropdown approval payload, disabled state, legacy-only configuration and unchanged preview geometry. Build passed and updated screenshot inspected; no EXE packaging.

## Consistency Revision - 2026-09-30

Supersedes the initial sections layout below. Both sections now use the same business-types button styles and identical heading/quantity layout. Regular types are all visible (no dropdown), with no generic instructional sentence. The joint-company switch remains separate from type selection. User feedback showed the earlier shortcut/radio split created unnecessary inconsistency.

The preview toggle lives only in the sidebar header, with fixed width for both labels. Tests reproduced a 1px x shift from the responsive border reset; preserving that border fixes it. Geometry assertions pass for 840/700px to 400px collapse at mocked 150% DPI; the same pointer coordinates restore the preview. Resize errors preserve expanded state. Matching tag styles, system badge alignment, quantity alignment, independent request arguments, disabled states, legacy options, debug safety and narrow views pass in Temp/verify_business_sections.py. Built screenshots inspected; actual desktop window resizing and office approval remain untested. No EXE rebuild or release.

## Business Sections - 2026-09-30

- Built UI verified in isolated Edge with every Tauri command mocked. No live approvals or registration writes.
- Regular menu: 10 options from the original 14 after separating 3 joint-company types and merging the legacy asset-operation type. Custom options remain available.
- Quick choices and full menu share selection. Core/OA commands receive independent type and quantity values. Running locks both sections and the switch; debug mode still disables OA.
- Checked default-off switch, hide/reopen selection, legacy-only asset options, missing joint options, light/dark themes and 840/700/400/360px layouts. Main approval buttons fit above the log bar at 840x740; sidebar scrolls for lower utilities.
- Frontend build and Temp/verify_business_sections.py passed. Screenshots inspected at Temp/business-sections-on.png and Temp/business-sections-off.png. Desktop EXE has not been rebuilt; office verification remains pending.

## Collapse Vertical Stability Fix

Release rebuilt and main executable updated in both dist_green and dist_share. Current SHA256: `3D0617EAB454469C1ABFD110DF9C245EC0309920B197EB9AFED2DD6848849283`. Both editions retain identical runtime files and the previous department-fix runner. No configuration replaced; not committed or pushed in this follow-up.

Reproduced the reported upward shift: the 800px viewport breakpoint reduced sidebar padding from 16px to 14px, gaps from 8px to 6px, action-card padding and button font size when folding to 400px. The breakpoint now changes sidebar width only. Before-fix geometry assertion failed at the logo (y=16 to y=14); after-fix checks pass for the y position and height of logo, steps, parameters, action card, registration summary and preview toggle (tolerance under 1px). Frontend build and isolated UI suite passed; compact screenshot inspected. Native window resizing remains simulated, not a unit-office verification.

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
