# Validation Patterns

## How Validation Works in A2UI v0.9

Validation is protocol-native via the `checks` array on FormField components. The renderer evaluates check conditions reactively — when the bound data changes, checks re-evaluate automatically.

### Display Gate: `__showValidation`

Errors are only SHOWN when `__showValidation` is `true`. This prevents showing errors before the user has interacted.

Pattern:

1. Initialize `"__showValidation": false` in data model
2. Bind FormField: `"showValidation": {"path": "/__showValidation"}`
3. On submit, the host application sets `/__showValidation` to `true`
4. All failing checks display their error messages

### Check Rule Structure

```json
{
  "condition": {
    "call": "<function-name>",
    "args": {
      "<param>": <DynamicValue>
    }
  },
  "message": "Human-readable error message"
}
```

- `condition` evaluates to boolean — `true` means VALID (no error)
- `message` displays when condition is `false` AND showValidation is `true`
- Multiple checks on one field display the FIRST failing message

## Built-in Validation Functions

These are available when the catalog includes BASIC_FUNCTIONS (check the catalog's `functions` section).

### required

Passes if value is not null, undefined, empty string, or empty array.

```json
{ "call": "required", "args": { "value": { "path": "/form/name" } } }
```

### regex

Passes if value matches the regular expression pattern.

```json
{ "call": "regex", "args": { "value": { "path": "/form/phone" }, "pattern": "^\\+?\\d{10,15}$" } }
```

Note: Backslashes in regex patterns MUST be double-escaped in JSON (`\\d` not `\d`).

### email

Passes if value matches basic email format.

```json
{ "call": "email", "args": { "value": { "path": "/form/email" } } }
```

### length

Passes if string length is within bounds. At least one of min/max required.

```json
{ "call": "length", "args": { "value": { "path": "/form/code" }, "min": 6, "max": 6 } }
```

### numeric

Passes if number is within bounds. Strings coerced to numbers.

```json
{ "call": "numeric", "args": { "value": { "path": "/form/amount" }, "min": 0, "max": 1000000 } }
```

## Comparison Functions

### equals / not_equals

```json
{ "call": "equals", "args": { "a": { "path": "/form/confirm" }, "b": { "path": "/form/password" } } }
```

### greater_than / less_than

```json
{ "call": "greater_than", "args": { "a": { "path": "/form/end_date" }, "b": { "path": "/form/start_date" } } }
```

## Logical Combinators

### and — all conditions must pass

```json
{
  "call": "and",
  "args": {
    "values": [
      { "call": "required", "args": { "value": { "path": "/form/field" } } },
      { "call": "length", "args": { "value": { "path": "/form/field" }, "min": 3 } }
    ]
  }
}
```

### or — at least one condition must pass

```json
{
  "call": "or",
  "args": {
    "values": [
      { "call": "equals", "args": { "a": { "path": "/form/type" }, "b": "other" } },
      { "call": "required", "args": { "value": { "path": "/form/details" } } }
    ]
  }
}
```

### not — negate a condition

```json
{ "call": "not", "args": { "value": { "call": "equals", "args": { "a": { "path": "/form/status" }, "b": "locked" } } } }
```

## Common Validation Recipes

### Required text field

```json
"checks": [
  {"condition": {"call": "required", "args": {"value": {"path": "/form/name"}}}, "message": "Name is required"}
]
```

### Required with format

```json
"checks": [
  {"condition": {"call": "required", "args": {"value": {"path": "/form/account"}}}, "message": "Account ID is required"},
  {"condition": {"call": "regex", "args": {"value": {"path": "/form/account"}, "pattern": "^\\d{12}$"}}, "message": "Must be exactly 12 digits"}
]
```

### Required email

```json
"checks": [
  {"condition": {"call": "required", "args": {"value": {"path": "/form/email"}}}, "message": "Email is required"},
  {"condition": {"call": "email", "args": {"value": {"path": "/form/email"}}}, "message": "Enter a valid email address"}
]
```

### Numeric range

```json
"checks": [
  {"condition": {"call": "required", "args": {"value": {"path": "/form/amount"}}}, "message": "Amount is required"},
  {"condition": {"call": "numeric", "args": {"value": {"path": "/form/amount"}, "min": 1, "max": 999999}}, "message": "Amount must be between 1 and 999,999"}
]
```

### File upload required

```json
"checks": [
  {"condition": {"call": "required", "args": {"value": {"path": "/form/files"}}}, "message": "At least one file is required"}
]
```

## FormField Props Reference

| Prop           | Type           | Description                                            |
| -------------- | -------------- | ------------------------------------------------------ |
| label          | DynamicString  | Field label (required)                                 |
| description    | DynamicString  | Help text below label                                  |
| constraintText | DynamicString  | Always-visible hint (e.g., "Required — max 100 chars") |
| errorText      | DynamicString  | Manual error override (prefer checks instead)          |
| showValidation | DynamicBoolean | Gate for displaying check errors                       |
| checks         | CheckRule[]    | Validation rules                                       |
| children       | ChildList      | The input component(s)                                 |

## Best Practices

1. Always put `required` as the FIRST check — it prevents other checks from running on empty values
2. Use `constraintText` to communicate requirements BEFORE the user submits (always visible)
3. Use `checks.message` for POST-submit error feedback (only shown when validation triggered)
4. Keep error messages specific and actionable ("Must be exactly 12 digits" not "Invalid input")
5. Initialize `__showValidation: false` — let the host control when errors appear
6. Never nest a required `FormField` under a conditionally `visible` ancestor in
   a submitted surface. Hidden required fields are still validated. Submit the
   branch choice first as a default-selected choice form, then render a separate
   form containing only the selected branch's fields.

## Component-Specific Authoring Notes

### Native message suggestions

Use native message suggestions only for short actions that require no
description or comparison. Pass one through five self-contained messages
with `suggest_replies`. Do not render
`SupportPromptGroup` or dispatch `atx:send-message` from `Button`,
`ActionCard`, or another inline component. When options need explanation, use
a default-selected `RadioGroup` with item descriptions and a `SubmitButton`.
Reserve `atx:submit` for a real form with values bound under `/form/*`.
When the complete form is rendered inside `SidePanelContent`, its
`SubmitButton` MUST explicitly set `action: "atx:submitAndClosePanel"`.
Use plain `atx:submit` (or the SubmitButton default) only for inline forms.
