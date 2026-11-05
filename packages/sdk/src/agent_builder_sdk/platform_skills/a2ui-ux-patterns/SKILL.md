---
name: a2ui-ux-patterns
description: >
  Choose customer-friendly A2UI interaction and presentation patterns for AWS
  Transform WebApp jobs. Use when deciding between suggestions, forms, tables,
  side panels, uploads, downloads, or plain text; pair with a2ui-rendering for
  the component and protocol contract.
---

# A2UI UX Patterns

Use this skill to decide how the customer should experience information and
actions. Load `a2ui-rendering` as well for the authoritative component catalog,
data-binding rules, action schemas, and delivery protocol.

## Eligibility

Apply these patterns only in an AWS Transform WebApp job where
`render_a2ui_surface` is available. MCP clients, CLI clients, and other
non-WebApp transports cannot render A2UI; use concise plain text or the
client's ordinary structured result there.

The customer does not need to know about A2UI, component names, the catalog,
or renderer limitations. Infer the best supported experience from what must be
displayed or collected.

## Choose the Interaction

Before sending a response, classify the customer need:

1. **Conversation only** — use plain text for a short status, explanation, or
   error that does not need structured display or customer input.
2. **Quick single-click action** — attach native message suggestions only when
   each short suggestion is self-explanatory and clicking it gives the agent
   everything needed to continue without displaying a description or tradeoff.
   Attach them with `suggest_replies`, whether or not a surface is also
   rendered.
3. **Structured data collection** — use a form with inputs, validation, and a
   `SubmitButton` when the customer must enter data, upload a file, make
   a selection whose options need explanation, make multiple selections, or
   return validated `/form/*` values.
4. **Structured information** — select the most compact catalog-supported
   visual that makes the data easy to scan and act on.

Never use native suggestions as a substitute for presenting explanations or
tradeoffs. If the customer must read descriptive option content before choosing,
render a form even when only one value is collected.

For richer decisions, choose controls based on the shape of the comparison:

- Prefer `RadioGroup` with each item's `description` for mutually exclusive
  choices that need explanation, such as workflow paths, strategies, or modes.
- Use `Tiles` for a small set of visual choices when their labels and concise
  descriptions fit the component better.
- Use `Select` or `Autosuggest` for a longer single-choice list.
- Use `Cards` for alternatives with several comparable attributes.
- Use a selectable `Table` for many structured candidates that benefit from
  filtering, sorting, or pagination.

Include concise labels and descriptions so tradeoffs are easy to scan. Bind
values under `/form/*` and use `SubmitButton` only when the interaction is
genuinely a form.

## Suggestions: One Click, Then Continue

Use native message suggestions to minimize typing and unnecessary confirmation
steps.

- Do not render `SupportPromptGroup` inside A2UI.
- Do not render suggestion boxes, clickable decision cards, or any inline A2UI
  component that dispatches `atx:send-message`.
- Attach one through five native message suggestions to the response with
  `suggest_replies`.
- The suggestion text becomes the customer's next message, so write it as a clear,
  self-contained instruction the agent can act on.
- Do not add radio buttons, a separate Continue button, a `/form/*` binding, or
  `atx:submit`.
- Native suggestions disappear after use, so they do not leave stale controls
  attached to a historical A2UI surface.

Use suggestions only for short actions that need no supporting description,
for example:

- Proceed to migration planning
- Run the full assessment
- Validate inventory quality
- Refresh this view

If options need explanatory text, render a default-selected `RadioGroup` form
with descriptions and a `SubmitButton`. The submitted form becomes completed
UI instead of leaving reusable inline action boxes behind.

`atx:submit` is for forms only.

## Forms: Collect Actual Values

Use a form when the agent needs customer-supplied data rather than merely a
workflow branch. Prefer combining related questions into one form instead of
serially asking one question per turn.

- Treat every interactive form's `surface_id` as customer-visible copy. After
  submission, the WebApp displays `Form <surface name> submitted`, where it
  expands camel case, kebab case, or snake case into lowercase words. Choose a
  concise kebab-case noun phrase that completes that sentence naturally and
  describes what the customer supplied or decided, for example
  `migration-preferences`, `assessment-assumptions`,
  `target-account-details`, or `migration-journey-selection`.
- Do not use an action phrase such as `collect-name`, a generic identifier such
  as `input`, `options`, or `form`, or implementation language such as
  `surface`, `submitted`, a UUID, or a version number in an interactive form
  `surface_id`. Do not append `-form`; the surrounding WebApp copy already says
  "Form".
- Stable technical IDs remain appropriate for readonly surfaces because they
  do not produce the form-submission confirmation.
- Keep readonly information and interactive forms in separate A2UI surfaces.
  It is valid and preferred to stage multiple A2UI surfaces in one message:
  present readonly summaries, status, tables, charts, and supporting context
  in one or more surfaces, then present the form in its own surface. This keeps
  the submitted overlay scoped to the form instead of dimming unrelated
  information.
- Keep details needed to answer a form next to the relevant controls by using
  the form title, instructions, `FormField` label or description, and option
  descriptions. Additional context that is not needed to understand a control
  belongs in a separate readonly surface.
- Combine related controls into one form surface. Do not split one logical form
  across multiple A2UI blocks.
- Bind collected values under `/form/*`.
- Initialize every bound path and set `__showValidation` to `false`.
- Add appropriate `FormField` validation and one `SubmitButton`.
- Use `atx:submit` for forms. Never use `atx:send-message` inside an A2UI
  surface; message suggestions are attached only through `suggest_replies`.
- Use `MultiStepForm` when several related inputs are easier to complete in
  stages.
- Every radio group, card selection, select, or other required choice must have
  a sensible default selection. The customer can change it before submitting.
- Prefill every form control whose value the agent already knows.
- When the customer asks to change something, offer an editable form with
  controls adapted to the data type and current values.
- Use a focused inline form for up to three controls. More than three controls
  is a hard threshold: the complete form, including its `SubmitButton`, MUST be
  a child of `SidePanelContent`. Inline content should contain only a concise
  explanation and a descriptive trigger such as "Open assessment settings".
- Every form rendered inside `SidePanelContent` MUST set its
  `SubmitButton.action` to `atx:submitAndClosePanel`. Do not rely on the
  `SubmitButton` default, because that dispatches plain `atx:submit` and leaves
  the completed panel open. The close-panel action still keeps the panel open
  when the next surface update contains validation errors or more fields.
- Inline forms must use plain `atx:submit` or the `SubmitButton` default; do
  not use `atx:submitAndClosePanel` outside `SidePanelContent`.
- Put actual defaults in the initial `/form/*` data model. Placeholder text,
  examples, and phrases such as "defaults to 1.0" do not initialize a control.
- Prefill inventory-derived values such as server count, storage total,
  existing configuration, region, and account whenever they are already
  available in the conversation or operation result.
- After submission, use the returned values without asking the customer to
  retype them.

Examples include account and region configuration, several assessment
assumptions, selecting multiple servers, and uploading inventory files.

## Uploads

If a file is the immediate input needed, show `FileUpload` directly. Do not
first ask the customer to choose an Upload option and then ask them to upload
in a second turn. If inline upload is unavailable, directly tell the customer
to use the chat attachment control.

When upload is optional but useful, show the upload control directly alongside
the current result or next actions. The customer may use it or ignore it; do
not ask whether they want an upload control.

When Upload is one of several genuinely different workflow branches, the
branch itself may be a native message suggestion; render `FileUpload`
immediately after that branch is selected.

## Tables and Summaries

- Never put raw HTML or Markdown formatting in A2UI component props or bound
  display values. Every string inside an A2UI surface is literal plain text;
  syntax such as `<strong>`, `**bold**`, Markdown headings, lists, links, and
  backticks may become visible garbage instead of formatting the content.
  Markdown belongs only in ordinary chat text outside the A2UI surface.
- Express structure and emphasis with catalog components. For example, render
  `Move grouping: skipped — using applications directly.` with a `Header` or
  another catalog-supported emphasis component, then put the explanatory
  paragraph in a separate `TextContent`. Use `SpaceBetween`, `ColumnLayout`,
  `KeyValuePairs`, `StatusIndicator`, `Badge`, and other appropriate native
  components instead of encoding their appearance in a text string.
- Choose by data shape, not by the number of facts.
- Use `ColumnLayout` for one entity, object, state, or snapshot expressed as
  heterogeneous label/value facts. This includes planning inventory,
  ingestion, assessment, configuration, and submission summaries, even when
  there are many facts. A synthetic two-column `Metric`/`Value`,
  `Key`/`Value`, or `Label`/`Value` table is an anti-pattern for this shape.
- Always place `ColumnLayout` inside a `Container`. The container supplies the
  visual boundary for the detail summary; reference the container, not the
  bare column layout, from the surrounding surface structure.
- Put one compact fact presentation in each `ColumnLayout` child and use two
  or three responsive columns as space permits. Preserve meaningful groupings
  instead of treating unrelated fields as comparable rows. Use a native
  `Header` for each group label rather than embedding HTML heading or strong
  tags in `TextContent`.
- Never flatten three or more labeled facts or assumptions into one prose or
  bullet block such as `Industry: ... - Revenue: ... - Servers: ...`. Use
  compact `KeyValuePairs` groups as the children of a `ColumnLayout`, and wrap
  that layout in a `Container`.
- Use resolved literal strings for display-component text, including
  `TextContent`, `Header`, `StatusIndicator`, `Badge`, and `Box`. Do not bind
  those components' `children` to a path in the current WebApp renderer.
- Use a sortable `Table` for spreadsheet or CSV data and repeated homogeneous
  records: each row is another instance of the same schema and users benefit
  from comparing the rows. Add filtering and pagination only at the threshold
  below. A two-column table is valid when it contains repeated records such as
  `Server`/`Status`, not generic labels and values for one object.
- If only one record is available, use `ColumnLayout` instead of a table,
  including when that record would otherwise appear as a two-column table.
- For fewer than 25 items, omit filtering, pagination, and `pageSize`; those
  controls add clutter without helping the user.
- For 25 or more items, enable filtering and pagination and set `pageSize` to
  no more than 25 items. Never render more than 25 items on one table page.
- Make every meaningful data column sortable.
- Add a heading directly above a table only when the message contains multiple
  tables and headings are needed to distinguish them. A single table should
  rely on the message or section context rather than a redundant table heading.
- Keep each `KeyValuePairs` group compact. For more than three total facts,
  place meaningfully grouped `KeyValuePairs` components inside a
  `ColumnLayout` wrapped by a `Container`.
- Do not split a larger summary into several sparse key/value groups.
- Keep alerts for status or caveats; do not use them as a substitute for the
  primary data presentation.
- Keep the most useful columns visible. Put substantial supporting detail in
  `SidePanelContent`.

For CSV or spreadsheet data, render a bounded table preview. If the customer
requests the original file, expose it with `atx:download-artifact`; do not add
a duplicate built-in attachment for content already shown inline. Include the
workspace scope whenever it is available. Include the job scope only when the
artifact is job-scoped and its owning job is known; omit it for workspace-level
artifacts even when the current chat is inside a job.

## Documents and Side Panels

For substantial Markdown or textual content, keep the chat response concise
and place the full readable content in `SidePanelContent`. Add a download
action only when the customer needs the source file. Do not render the same
content inline, in the side panel, and as an attachment.

Use `SidePanelContent` for long reports, lengthy body text, complex contextual
material, and forms with more than three controls. This is mandatory for a
report with three or more tabs or three or more tables: render only a concise
summary and descriptive panel trigger inline, and place the detailed report
inside the panel. One compact summary table may remain inline; every detailed
table and any tab group with three or more tabs must be a descendant of the
`SidePanelContent` component. Use the exact catalog shape:
`{"component":"SidePanelContent","label":"Open full report","children":["report"]}`.
Do not invent `trigger`, `header`, or `width` props.

## Alerts

Use alert severity according to meaning:

- Warning and error alerts communicate warnings, blocked states, failures, or
  required attention.
- Info alerts communicate optional or additional context that is not the
  primary content of the current message, such as an extra capability, an
  unexpected secondary finding, or helpful background.

Do not place the message's normal primary result in an info alert.
Do not put action-oriented instructions such as “upload your file,” “choose an
option,” or “enter these values” in an info alert. Use ordinary text,
`TextContent`, or the relevant `FormField` description.

## Charts, Graphs, and Diagrams

Use charts, graphs, and diagrams when they make contrasts, changes over time,
or large data relationships easier to understand than a table or prose.
Include accessible labels and keep the underlying facts available in a table
or side-panel detail when the visualization alone would hide precision.

Give each `MermaidDiagram` its own row: make it, or a `Container` that wraps
only it, a child of a vertical `SpaceBetween`. Never place one inside
`ColumnLayout`, `Grid`, or a `SpaceBetween` with `direction: "horizontal"`.

## Preferences and Component Quality

- Honor an explicit customer preference for how data is displayed whenever the
  catalog supports it.
- Follow Cloudscape UX guidance for component choice, defaults, labels,
  validation, density, and responsive layout.
- Prefer useful defaults and direct actions over making the customer type,
  confirm an obvious intermediate step, or repeat known information.

## Next Actions

Do not end with “What would you like to do next?” Instead:

- proactively show the useful result or state the customer would otherwise
  need to ask for;
- introduce the actions with language such as “Here is what I can do for you
  now” or “Which of these would you like me to do next?”; and
- attach prepopulated native message suggestions, or render the directly usable
  form when actual data collection is required.

## Final UX Check

Before sending:

- replace Markdown tables or repeated-record prose with an A2UI table;
- replace every one-record table with a `ColumnLayout`;
- wrap every `ColumnLayout` in a `Container`;
- replace dense labeled-fact prose with grouped `KeyValuePairs` inside that
  contained `ColumnLayout`;
- keep descriptive single-choice decisions as default-selected `RadioGroup`
  forms with a `SubmitButton`;
- verify every interactive form has a concise customer-facing `surface_id`
  that reads naturally in `Form <surface name> submitted`;
- ensure `SupportPromptGroup` is absent from the A2UI surface;
- ensure no inline component dispatches `atx:send-message`;
- ensure `atx:submit` appears only on a real form with values to collect;
- ensure every required choice and known form value has a default;
- keep readonly information and the interactive form in separate A2UI blocks;
- combine related controls into one form instead of splitting the form across
  multiple blocks;
- move forms with more than three controls and long content to a side panel;
- verify every side-panel form uses `atx:submitAndClosePanel` and every inline
  form uses plain `atx:submit`;
- verify advertised defaults are actual initialized values, not placeholders;
- omit filtering and pagination below 25 rows; at 25 or more rows, enable both
  and keep every page at 25 rows or fewer;
- give each `MermaidDiagram` its own row in a vertical `SpaceBetween`, never
  inside `ColumnLayout`, `Grid`, or a horizontal `SpaceBetween`;
- attach only one set of native message suggestions;
- verify alerts are reserved for warnings, errors, or genuinely secondary info;
- remove HTML and Markdown formatting syntax from every A2UI component prop and
  bound display value, expressing the intended structure with native catalog
  components instead;
- remove duplicate artifacts for content already rendered inline; and
- keep final prose to one short neutral sentence that does not describe,
  summarize, or repeat the surface.
