# Common HITL UI Patterns

## Overview

This guide provides ready-to-use JSON templates for common HITL UI scenarios. Copy and customize these patterns for your needs.

## Pattern 1: Single File Upload

**When to use:** Agent needs a specific missing file from the user.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Upload Missing File"]
    },
    {
      "type": "Alert",
      "props": { "type": "info" },
      "children": [
        "The transformation requires abc.js to continue. Please upload it below."
      ]
    },
    {
      "type": "FileUpload",
      "props": {
        "fieldId": "missingFile",
        "multiple": false,
        "accept": ".js",
        "constraintText": "Upload a single JavaScript file"
      }
    }
  ]
}
```

**Customization:**

- Change file type in `accept` prop
- Modify alert message
- Add `showFileSize: true` to display file size

---

## Pattern 2: Multiple File Upload with Constraints

**When to use:** Agent needs multiple files with specific requirements.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Upload Configuration Files"]
    },
    {
      "type": "Alert",
      "props": { "type": "warning" },
      "children": ["Please upload all required configuration files (.json, .yaml, .yml)"]
    },
    {
      "type": "FileUpload",
      "props": {
        "fieldId": "configFiles",
        "multiple": true,
        "accept": ".json,.yaml,.yml",
        "showFileSize": true,
        "showFileLastModified": true,
        "constraintText": "Upload up to 10 files (max 5MB each)"
        }
      }
    }
  ]
}
```

---

## Pattern 3: Simple Text Form (2-3 inputs)

**When to use:** Collect basic information from user.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Contact Information"]
    },
    {
      "type": "FormField",
      "props": { "label": "Name", "constraintText": "Enter your full name" },
      "children": [
        {
          "type": "Input",
          "props": {
            "fieldId": "userName",
            "placeholder": "John Doe"
          }
        }
      ]
    },
    {
      "type": "FormField",
      "props": {
        "label": "Email Address",
        "constraintText": "We'll send updates to this email"
      },
      "children": [
        {
          "type": "Input",
          "props": {
            "fieldId": "userEmail",
            "type": "email",
            "placeholder": "john@example.com"
          }
        }
      ]
    }
  ]
}
```

**Note:** No submit button needed — the platform handles submission automatically.

---

## Pattern 4: Data Table (Basic)

**When to use:** Display structured data for review.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Transformation Results"]
    },
    {
      "type": "Table",
      "props": {
        "variant": "borderless",
        "columnDefinitions": [
          { "header": "File Name", "field": "fileName" },
          { "header": "Status", "field": "status" },
          { "header": "Lines Changed", "field": "linesChanged" }
        ],
        "items": [
          {
            "id": "1",
            "fileName": "app.js",
            "status": "Success",
            "linesChanged": "45"
          },
          {
            "id": "2",
            "fileName": "config.json",
            "status": "Success",
            "linesChanged": "12"
          },
          {
            "id": "3",
            "fileName": "README.md",
            "status": "Skipped",
            "linesChanged": "0"
          }
        ]
      }
    }
  ]
}
```

---

## Pattern 5: Data Table with Status Indicators

**When to use:** Display data with visual status indicators.

```json
{
  "type": "Table",
  "props": {
    "variant": "borderless",
    "header": "File Processing Status",
    "columnDefinitions": [
      { "header": "File", "field": "file" },
      { "header": "Status", "field": "status" }
    ],
    "items": [
      {
        "id": "1",
        "file": "app.js",
        "status": "{\"type\": \"StatusIndicator\", \"props\": {\"type\": \"success\"}, \"children\": [\"Completed\"]}"
      },
      {
        "id": "2",
        "file": "test.js",
        "status": "{\"type\": \"StatusIndicator\", \"props\": {\"type\": \"in-progress\"}, \"children\": [\"Processing\"]}"
      },
      {
        "id": "3",
        "file": "config.json",
        "status": "{\"type\": \"StatusIndicator\", \"props\": {\"type\": \"error\"}, \"children\": [\"Failed\"]}"
      }
    ]
  }
}
```

**Note:** Table cells can contain JSON-encoded components for rich content.

---

## Pattern 6: Dashboard with Metrics

**When to use:** Show summary statistics and key metrics.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h1" },
      "children": ["Transformation Summary"]
    },
    {
      "type": "ColumnLayout",
      "props": { "columns": 3 },
      "children": [
        {
          "type": "SpaceBetween",
          "props": { "direction": "vertical", "size": "s" },
          "children": [
            {
              "type": "Header",
              "props": { "variant": "h3" },
              "children": ["Total Files"]
            },
            {
              "type": "Box",
              "props": {
                "fontSize": "heading-xl",
                "textAlign": "center",
                "padding": "l"
              },
              "children": ["125"]
            }
          ]
        },
        {
          "type": "SpaceBetween",
          "props": { "direction": "vertical", "size": "s" },
          "children": [
            {
              "type": "Header",
              "props": { "variant": "h3" },
              "children": ["Success Rate"]
            },
            {
              "type": "Box",
              "props": {
                "fontSize": "heading-xl",
                "textAlign": "center",
                "padding": "l"
              },
              "children": ["98%"]
            }
          ]
        },
        {
          "type": "SpaceBetween",
          "props": { "direction": "vertical", "size": "s" },
          "children": [
            {
              "type": "Header",
              "props": { "variant": "h3" },
              "children": ["Duration"]
            },
            {
              "type": "Box",
              "props": {
                "fontSize": "heading-xl",
                "textAlign": "center",
                "padding": "l"
              },
              "children": ["2.5 min"]
            }
          ]
        }
      ]
    }
  ]
}
```

---

## Pattern 7: Dashboard with Pie Chart

**When to use:** Show proportional data distribution.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["File Status Distribution"]
    },
    {
      "type": "PieChart",
      "props": {
        "data": [
          { "title": "Success", "value": 85, "color": "#1d8102" },
          { "title": "Warning", "value": 10, "color": "#ff9900" },
          { "title": "Failed", "value": 5, "color": "#d13212" }
        ]
      }
    }
  ]
}
```

---

## Pattern 8: Approval/Rejection UI

**When to use:** User needs to approve or reject transformation results.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Review Transformation Results"]
    },
    {
      "type": "Alert",
      "props": { "type": "info" },
      "children": [
        "Please review the changes and approve or reject the transformation."
      ]
    },
    {
      "type": "FormField",
      "props": { "label": "Decision" },
      "children": [
        {
          "type": "RadioGroup",
          "props": {
            "fieldId": "decision",
            "items": [
              { "value": "approve", "label": "Approve - Apply all changes" },
              { "value": "reject", "label": "Reject - Discard all changes" },
              {
                "value": "review",
                "label": "Request Review - Need more information"
              }
            ]
          }
        }
      ]
    },
    {
      "type": "FormField",
      "props": { "label": "Comments (Optional)" },
      "children": [
        {
          "type": "Textarea",
          "props": {
            "fieldId": "comments",
            "placeholder": "Add any comments or feedback...",
            "rows": 4
          }
        }
      ]
    }
  ]
}
```

**Note:** No submit button needed — the platform handles submission. Agent receives:

```json
{ "decision": "approve", "comments": "Looks good" }
```

---

## Pattern 9: File Selection from List

**When to use:** User needs to include/exclude specific files from a list.

**Note:** Multiselect and Checkbox do NOT capture input. Use one RadioGroup per file with Include/Exclude options instead.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Select Files to Transform"]
    },
    {
      "type": "Alert",
      "props": { "type": "info" },
      "children": [
        "Choose which files should be included in the transformation."
      ]
    },
    {
      "type": "FormField",
      "props": { "label": "src/app.js" },
      "children": [
        {
          "type": "RadioGroup",
          "props": {
            "fieldId": "file_app_js",
            "items": [
              { "value": "include", "label": "Include" },
              { "value": "exclude", "label": "Exclude" }
            ]
          }
        }
      ]
    },
    {
      "type": "FormField",
      "props": { "label": "src/config.json" },
      "children": [
        {
          "type": "RadioGroup",
          "props": {
            "fieldId": "file_config_json",
            "items": [
              { "value": "include", "label": "Include" },
              { "value": "exclude", "label": "Exclude" }
            ]
          }
        }
      ]
    },
    {
      "type": "FormField",
      "props": { "label": "src/utils.js" },
      "children": [
        {
          "type": "RadioGroup",
          "props": {
            "fieldId": "file_utils_js",
            "items": [
              { "value": "include", "label": "Include" },
              { "value": "exclude", "label": "Exclude" }
            ]
          }
        }
      ]
    }
  ]
}
```

**Agent receives:** `{ "file_app_js": "include", "file_config_json": "exclude", "file_utils_js": "include" }`

---

## Pattern 10: Configuration Form

**When to use:** Collect configuration parameters from user.

**Note:** Select and Checkbox do NOT capture input. Use RadioGroup for all selections.

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Transformation Configuration"]
    },
    {
      "type": "FormField",
      "props": { "label": "Target Framework" },
      "children": [
        {
          "type": "RadioGroup",
          "props": {
            "fieldId": "targetFramework",
            "items": [
              { "value": "react18", "label": "React 18" },
              { "value": "vue3", "label": "Vue 3" },
              { "value": "angular17", "label": "Angular 17" }
            ]
          }
        }
      ]
    },
    {
      "type": "FormField",
      "props": { "label": "Include Tests" },
      "children": [
        {
          "type": "RadioGroup",
          "props": {
            "fieldId": "includeTests",
            "items": [
              { "value": "yes", "label": "Yes - Generate unit tests for transformed code" },
              { "value": "no", "label": "No - Skip test generation" }
            ]
          }
        }
      ]
    },
    {
      "type": "FormField",
      "props": { "label": "Code Style" },
      "children": [
        {
          "type": "RadioGroup",
          "props": {
            "fieldId": "codeStyle",
            "items": [
              { "value": "standard", "label": "Standard" },
              { "value": "airbnb", "label": "Airbnb" },
              { "value": "google", "label": "Google" }
            ]
          }
        }
      ]
    }
  ]
}
```

---

## Combining Patterns

You can combine multiple patterns for complex UIs:

```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "xl" },
  "children": [
    {
      "type": "Header",
      "props": { "variant": "h1" },
      "children": ["Transformation Review"]
    },
    {
      "type": "Alert",
      "props": { "type": "success" },
      "children": [
        "Transformation completed successfully. Please review the results below."
      ]
    },
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Summary"]
    },
    {
      "type": "KeyValuePairs",
      "props": {
        "items": [
          { "label": "Files Processed", "value": "125" },
          { "label": "Success Rate", "value": "98%" },
          { "label": "Duration", "value": "2.5 minutes" }
        ]
      }
    },
    {
      "type": "Header",
      "props": { "variant": "h2" },
      "children": ["Detailed Results"]
    },
    {
      "type": "Table",
      "props": {
        "variant": "borderless",
        "columnDefinitions": [
          { "header": "File", "field": "file" },
          { "header": "Status", "field": "status" }
        ],
        "items": [
          { "id": "1", "file": "app.js", "status": "Success" },
          { "id": "2", "file": "config.json", "status": "Success" }
        ]
      }
    }
  ]
}
```

---

## Tips for Using Patterns

1. **Start with a pattern** - Find the closest match to your needs
2. **Customize gradually** - Change one thing at a time
3. **Test frequently** - Validate and test in Storybook after each change
4. **Combine patterns** - Use SpaceBetween to stack multiple patterns
5. **Keep it simple** - Don't over-complicate the UI

## Next Steps

- Test patterns in Storybook: `https://assets.transform-alpha-intg.us-west-2.on.aws/storybook/index.html?path=/story/components-hitlenginerenderer--playground&globals=locale:en`
- Validate JSON: Ask me to validate your customized pattern
- Learn more: See `component-library.md` for all available components
