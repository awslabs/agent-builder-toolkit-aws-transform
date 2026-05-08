# Creating Custom HITL UI Components

## Do You Need a Custom Component?

Before creating one, check if an existing component already works:

| Need | Existing Component | fieldId? |
|------|-------------------|----------|
| Text input | `Input` | Yes |
| Multi-line text | `Textarea` | Yes |
| File upload (auto base64) | `FileUpload` | Yes |
| Radio selection | `RadioGroup` | Yes |
| Data table (filter/paginate/sort) | `Table` | No display-only |
| Pie chart | `PieChart` | No display-only |
| Rich markdown | `Markdown` | No display-only |
| Loading skeleton | `ContentLoader` | No display-only |
| Any standard CloudScape component | Use `"type": "ComponentName"` directly | No no input capture |

**If an existing component works** → just use it in your JSON. No custom code needed.

**If you need a custom component** → choose your path:

### Path A: Wrap a CloudScape Component (Most Common)
You want a CloudScape component (e.g., `Select`, `DatePicker`) to **capture user input** and send it back to the agent. This adds it to the JSON rendering engine.

### Path B: Build a Domain-Specific Component (Advanced)
You need a complex, multi-component UI that can't be expressed as JSON (e.g., a connector wizard, a migration planner). This registers a standalone React component.

---

## Path A: Wrap a CloudScape Component

**End result:** Developers write `"type": "Select"` in JSON → engine renders your wrapped version → input captured via `fieldId`.

### Step 1: Create the Component

Create a file in `TransformUIComponents/src/DynamicHITLRenderEngine/Atoms/`:

```typescript
// MyWrappedSelect.tsx
import Select, { SelectProps } from '@amzn/awsui-components-react/polaris/select';
import { FC, useState } from 'react';
import { useFieldInput } from '../HITLCallbackContext';

// Extend CloudScape props with fieldId
interface WrappedSelectProps extends SelectProps {
  fieldId?: string;
}

export const WrappedSelect: FC<WrappedSelectProps> = (props) => {
  const { fieldId, disabled: propDisabled, ...restProps } = props;

  // useFieldInput gives you:
  //   handleValueChange(value) — saves to context keyed by fieldId
  //   disabled — true when task is completed or job is terminal
  const { handleValueChange, disabled: contextDisabled } = useFieldInput(fieldId);

  const [selectedOption, setSelectedOption] = useState<SelectProps.Option | null>(null);

  const handleChange = ({ detail }: { detail: SelectProps.ChangeDetail }) => {
    setSelectedOption(detail.selectedOption);
    handleValueChange(detail.selectedOption.value);  // Agent receives this value
  };

  return (
    <Select
      {...restProps}
      onChange={handleChange}
      selectedOption={selectedOption}
      disabled={contextDisabled || propDisabled}  // Always merge both
    />
  );
};
```

**The pattern is always the same:**
1. Extend CloudScape props with `fieldId?: string`
2. Call `useFieldInput(fieldId)` → get `handleValueChange` + `disabled`
3. Local state for UI, `handleValueChange` for context
4. Merge disabled: `contextDisabled || propDisabled`

### Step 2: Register in the Rendering Engine

In `DynamicHITLRenderEngine.tsx`, add your component to `totalComponent`:

```typescript
import { WrappedSelect } from './Atoms/MyWrappedSelect';

const totalComponent = {
  ...Cloudscape,
  // ... existing overrides
  Select: WrappedSelect,  // ← Add here. Key = JSON "type" name
};
```

### Step 3: Export

In `DynamicHITLRenderEngine/index.tsx`:

```typescript
export { WrappedSelect } from './Atoms/MyWrappedSelect';
```

### Step 4: Update the JSON Schema

If your component is already a CloudScape component (like `Select`), it's already in the schema enum — no change needed.

If it's a brand new type name, add it to the `enum` in the schema:
```json
"enum": [ ..., "MyNewComponent" ]
```

And optionally add prop validation:
```json
{
  "if": { "properties": { "type": { "const": "MyNewComponent" } } },
  "then": {
    "properties": {
      "props": {
        "properties": {
          "myRequiredProp": { "type": "string" }
        },
        "required": ["myRequiredProp"]
      }
    }
  }
}
```

### Step 5: Test

1. Build the package: `npm run build`
2. Open Storybook: `https://assets.transform-alpha-intg.us-west-2.on.aws/storybook/index.html?path=/story/components-hitlenginerenderer--playground&globals=locale:en`
3. Paste test JSON:
```json
{
  "type": "FormField",
  "props": { "label": "Choose Option" },
  "children": [
    {
      "type": "Select",
      "props": {
        "fieldId": "userChoice",
        "placeholder": "Pick one",
        "options": [
          { "label": "Option A", "value": "a" },
          { "label": "Option B", "value": "b" }
        ]
      }
    }
  ]
}
```
4. Verify: Component renders, selection works, submit button enables after selection

### Step 6: Create CR and Deploy

1. Commit changes to `TransformUIComponents`
2. Create CR: `cr --summary "[TransformUIComponents] Add wrapped Select component"`
3. After merge, the component is available to all teams using the rendering engine

---

## Path B: Domain-Specific Component

**End result:** Agent creates HITL task with `uxComponentId: "YourComponent"` → platform renders your standalone React component.

Use this when your UI is too complex for JSON (multi-step wizards, custom visualizations, components with API calls).

### Step 1: Create the Component

Create in `TransformUIComponents/src/YourComponent/`:

```typescript
// YourComponent.tsx
import { FC } from 'react';

interface YourComponentProps {
  // Props come from agentArtifact.properties (spread by HITLRenderEngine)
  title: string;
  data: any[];
  onInputChange: (data: any) => void;  // Injected by platform
  metadata: Metadata;                   // Injected by platform
}

export const YourComponent: FC<YourComponentProps> = ({
  title, data, onInputChange, metadata
}) => {
  // Your complex UI logic here
  // Call onInputChange({...}) to save user responses
  return <div>...</div>;
};
```

**Props injected by the platform automatically:**
- `onInputChange` — Save user responses
- `onRefresh` — Trigger refresh
- `updateSubmitButtonState` / `updateSaveButtonState` — Control buttons
- `registerSubmitConfirmationHandler` — Custom confirmation dialog
- `metadata` — Task status, severity, workspace/job IDs
- `createArtifactDownloadUrl` — Download artifacts
- `data` — Previously saved human input (for resuming)

### Step 2: Register in componentRegistry

In `componentRegistry.ts`:

```typescript
import { YourComponent } from './YourComponent';

export const componentRegistry: ComponentRegistry = {
  // ... existing 100+ components
  YourComponent,
};
```

### Step 3: Create Agent Artifact

Your agent creates an artifact with props for your component:

```json
{
  "properties": {
    "title": "Review Migration Plan",
    "data": [...]
  }
}
```

The platform spreads `properties` as props: `<YourComponent {...agentArtifact.properties} />`.

### Step 4: Create HITL Task

Agent creates task with your component ID:
```
uxComponentId: "YourComponent"
agentArtifact: { artifactId: "<id>" }
```

---

## Reference: HITL Context API

### `useFieldInput(fieldId?)` — For Input Components

```typescript
const { handleValueChange, disabled } = useFieldInput(fieldId);
```

| Property | Type | Description |
|----------|------|-------------|
| `handleValueChange` | `(value: unknown) => void` | Saves value to context keyed by fieldId |
| `disabled` | `boolean` | True when task completed or job terminal |

If `fieldId` is omitted, auto-generates one via React's `useId()`. Always prefer explicit `fieldId` for meaningful agent responses.

### `useHITLContext()` — For Advanced Components

```typescript
const ctx = useHITLContext();
```

| Property | Type | Description |
|----------|------|-------------|
| `disabled` | `boolean` | Global disabled state |
| `updateInput` | `({ fieldId, value }) => void` | Direct input update |
| `onRefresh` | `() => void` | Trigger UI refresh |
| `registerSubmitConfirmationHandler` | `(handler) => void` | Custom submit confirmation |
| `registerSaveConfirmationHandler` | `(handler) => void` | Custom save confirmation |
| `registerRejectConfirmationHandler` | `(handler) => void` | Custom reject confirmation |
| `updateSaveButtonState` | `(state) => void` | Show/hide/disable save |
| `updateSubmitButtonState` | `(state) => void` | Show/hide/disable submit |
| `workspaceId` | `string?` | Current workspace |
| `jobId` | `string?` | Current job |
| `createArtifactDownloadUrl` | `(artifactId) => Promise<string?>` | Download URL generator |

---

## Existing Wrapped Components (for reference)

These are already registered in the engine — study them as examples:

| Component | File | Captures Input? | Notes |
|-----------|------|:-:|-------|
| TextInput | `Atoms/TextInput.tsx` | Yes | Simplest example |
| TextArea | `Atoms/TextArea.tsx` | Yes | Same pattern as TextInput |
| RenderFileUpload | `Atoms/FileUpload.tsx` | Yes | Converts to base64, detects zip |
| RadioGroupComponent | `Atoms/RadioGroups.tsx` | Yes | Auto-selects first item |
| TableWithRenderer | `Atoms/Table.tsx` | No | JSON cell rendering, pagination |
| WrappedPieChart | `Atoms/PieChart/` | No | i18n, custom popover |
| WrappedMarkdown | `Atoms/Markdown/` | No | GFM, syntax highlighting, deeplinks |
| ContentLoaderWrapper | `Atoms/ContentLoader.tsx` | No | Skeleton animation |

**Source:** `TransformUIComponents/src/DynamicHITLRenderEngine/Atoms`

---

## Support

- **Slack:** #atx-foundation-partner-ux
