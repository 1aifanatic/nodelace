# Nodelace language reference

Nodelace source files are UTF-8 text conventionally named `*.diagram`. A single
leading UTF-8 byte-order mark (BOM) is accepted. The
language describes meaning and relationships; Nodelace chooses coordinates and
routes connectors deterministically.

## Document structure

A document contains an optional header followed by edges and directives. Put
the header first when one is present. A document without a header is a `flow`
diagram.

```text
architecture "Service Map"
direction left-to-right

Client -> Gateway: request
Gateway -> Worker -> Database

group Runtime: Gateway, Worker
highlight Gateway
```

Blank lines are ignored. Comments begin with `#` or `//` at the start of a
line or after whitespace:

```text
# This is a whole-line comment.
A -> B  // This is an inline comment.
```

Comment markers inside quoted text are literal characters.

## Header

```text
architecture "Title"
flow "Title"
sequence "Title"
```

The kind controls layout semantics:

- `architecture` arranges components and system boundaries.
- `flow` arranges steps, branches, joins, and feedback paths.
- `sequence` preserves message order from top to bottom and arranges
  participants from left to right.

The quoted title is optional. If the complete header is omitted, Nodelace uses
`flow` with no title. A header appearing after another statement is an error.

## Nodes and names

An edge, group, or highlight introduces a node the first time its name appears.
Names are Unicode and may contain internal spaces:

```text
Order Form -> Risk Review
München -> 東京
```

Surround a name with double quotes when it contains language syntax such as
`->`, a comma, a colon, or a comment marker, or when leading or trailing space
is significant:

```text
"Input: CSV" -> Parser
Parser -> "Export -> Archive"
group "Read, write": Parser, "Export -> Archive"
```

Inside a quoted name, `\"` represents a double quote and `\\` represents a
backslash. Other backslash escapes are invalid. Surrounding whitespace on an
unquoted name is not part of the name.

Names are case-sensitive: `API` and `Api` are different nodes.

## Edges and chains

A directed edge uses `->`:

```text
A -> B
```

Add a label after a colon:

```text
A -> B: HTTPS
```

A chain expands from left to right:

```text
A -> B -> C
```

This is equivalent to:

```text
A -> B
B -> C
```

A label on a chain belongs only to its final edge. In the next example,
`accepted` labels `B -> C`; `A -> B` is unlabeled:

```text
A -> B -> C: accepted
```

In a sequence diagram, edge statements are messages and their source order is
their time order. A reverse edge is a later response, not a bidirectional
connector:

```text
sequence "Lookup"
Client -> Service: request
Service -> Store: query
Store -> Service: result
Service -> Client: response
```

## Direction

Architecture diagrams default to `left-to-right`; flow diagrams default to
`top-to-bottom`. Override either layout with one directive:

```text
direction left-to-right
```

The supported values are:

- `left-to-right`
- `top-to-bottom`

A second direction directive is an error. Sequence diagrams always use
left-to-right participant columns and top-to-bottom message time, so a
direction directive is rejected.

## Groups

Groups place related nodes inside a flat visual region:

```text
group Clients: Browser, Mobile
group Services: Gateway, Catalog, Orders
```

The group name and every member use the same name and quoting rules as nodes.
Groups do not create edges. They are available only in architecture and flow
diagrams; a group directive in a sequence diagram is rejected.

A group name may be declared only once. A node may appear only once in a group
declaration and may belong to only one group. Nested groups are not supported.

## Highlights

Use highlights sparingly to identify the focal node or nodes:

```text
highlight Gateway
highlight Orders, Payments
```

Highlighting changes presentation, not topology. Like a group declaration, a
highlight can introduce a node; a node cannot be highlighted twice.

## Informal grammar

This grammar summarizes statement shapes. `name` is either a quoted name or an
unquoted Unicode name that stops at the surrounding statement's delimiter.

```text
document       := [header] {blank | comment | statement}
header         := kind [quoted-title]
kind           := "architecture" | "flow" | "sequence"
statement      := direction | edge | group | highlight
direction      := "direction" ("left-to-right" | "top-to-bottom")
edge           := name "->" name {"->" name} [":" label]
group          := "group" name ":" name {"," name}
highlight      := "highlight" name {"," name}
comment        := ("#" | "//") text
```

## Validation and diagnostics

`nodelace check` parses and validates without writing a diagram:

```console
nodelace check architecture.diagram
```

Nodelace reports the source name and location for malformed syntax. Validation
also rejects contradictory declarations, including duplicate directions,
duplicate group names or members, membership in more than one group, duplicate
highlights, and sequence-only restrictions.

Programmatically, syntax failures raise `DiagramSyntaxError` and semantic
failures raise `DiagramValidationError`. Pass `source_name` when parsing text
to make diagnostics identify their origin:

```python
from nodelace import parse_diagram

diagram = parse_diagram(source, source_name="architecture.diagram")
```

To keep layout work bounded, a document may contain at most 50 nodes, 200
edges, and 20 groups. Titles and names are limited to 200 characters; edge
labels are limited to 500 characters. The CLI and `render_file` additionally
limit a source file to 256 KiB. These are safety ceilings, not density targets:
most published diagrams are clearer with far fewer elements.

## Semantic declarations (0.2)

```text
flow "Release gate"
node Gate shape=decision label="Ready?"
node Build role=backend tag=CI sublabel="Build and test"
node Done shape=terminal
Build -> Gate
Gate => Done: yes
Gate -> Build: no
```

`node ID` accepts `label`, `role`, `shape`, `tag`, and `sublabel` as `key=value`
attributes. Quote multiword IDs and values. Unknown/repeated attributes and
duplicate declarations fail. A declaration can follow an edge mentioning its ID.
Roles: `default`, `backend`, `store`, `external`, `input`, `optional`.
Shapes: `box`, `terminal`, `decision`, `merge`. Decision and merge shapes do not
accept tags/sublabels. A merge is a small circle whose name remains accessible.
Sequence participants accept box/terminal shapes only.

Arrows: `->` ordinary, `-->` return, `~>` asynchronous, `=>` primary.
`call A -> B: request` explicitly denotes a sequence call. Labels never determine
message kind. Returns are dashed; async messages have open arrowheads; primary
edges use the accent color.

```text
sequence "Sign in"
Browser -> API: authenticate
activate API
alt "valid credentials"
API --> Browser: session
else "invalid credentials"
API --> Browser: rejected
end
deactivate API
```

ALT requires two nonempty regions and an explicit `else` guard. OPT and LOOP
require a quoted guard and close with `end`. At most one nested level is supported;
nested frames cannot cross ALT branch boundaries. `activate NAME` and
`deactivate NAME` delimit explicit nonempty message ranges. Activations are never
guessed from labels. Unclosed regions and activations fail validation.

`check INPUT --layout` checks geometry, shortened text, contrast and editorial
budgets. `--strict` makes warnings fail too (exit 2). Pass the same `--theme`,
`--profile` and `--size` used for rendering. Inspect images before sharing.

## Complete examples

See the ten sources in [examples](../examples). They cover both layout
directions, labeled and chained edges, branching, flat groups, feedback cycles,
Unicode, and request/response sequences.
