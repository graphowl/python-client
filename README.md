# graphowl — Python client for GraphOWL

A typed Python client for the [GraphOWL](https://github.com/graphowl/graphowl) HTTP API: look up what a term means, browse an ontology, walk the graph, run reasoning and validation, and ask SPARQL or Cypher questions. Sync and async, with typed errors.

Status: **early access**, version 0.1.0. Not yet on PyPI. Requires Python 3.11 or newer; depends on `httpx` and `pydantic`.

To push data *in* from a script or scheduler job, use the dependency-free [`graphowl-ingest`](https://github.com/graphowl/sdk-python) instead.

## Install

```bash
pip install .          # from a checkout
```

## First calls

```python
from graphowl import GraphOWL

owl = GraphOWL(url="https://your-graphowl-host", api_key="...")

owl.vocabulary.search("invoice")        # what a business term means
owl.ontology.term_iris("demo")          # what types exist in a pack
owl.assets.list(limit=10)               # what is catalogued
owl.catalog.lineage(asset_id)           # where its values came from
owl.graph().subgraph(asset_id)          # what connects to what
owl.inference.run()                     # what can be derived
owl.validation.report()                 # whether the data is valid
owl.governance.policies()               # what is allowed
owl.query.sparql("SELECT * WHERE { ?s ?p ?o } LIMIT 5")   # ask exactly
```

## One client, grouped by what you want to do

The API's route table is an implementation detail. A caller should know the difference between a vocabulary term, an ontology class and a graph entity, and the client keeps them apart:

```python
owl.vocabulary.search("Invoice")                     # "what do people mean by invoice?"
owl.ontology.class_("demo:Invoice", pack="demo")     # "what type is this?"
owl.graph().entities(type="demo:Invoice")            # "what actual things exist?"
```

| Group | For |
|---|---|
| `vocabulary`, `ontology`, `modelling` | terms, classes and models, and proposing changes to them |
| `assets`, `catalog` | what is catalogued, its owners, domains and lineage |
| `graph`, `query`, `semantic` | walking the graph; SPARQL and Cypher; questions in words |
| `mapping`, `virtual_graphs` | aligning a source to the model; asking a source in place |
| `inference`, `validation`, `reconciliation` | what can be derived, whether it is valid, where two sides disagree |
| `governance`, `collaboration`, `webhooks` | policies and grants, an inbox and threads, outbound notifications |
| `workspaces`, `ops` | workspaces and their packs; server health |

## Async

```python
import asyncio
from graphowl import AsyncGraphOWL

async def main():
    async with AsyncGraphOWL(url="https://your-graphowl-host", api_key="...") as owl:
        assets, terms = await asyncio.gather(
            owl.assets.list(limit=3),
            owl.vocabulary.search("invoice"),
        )

asyncio.run(main())
```

Same surface, every call awaitable, one implementation. Calls run on worker threads: right for an application backend, not for fanning out hundreds at once.

## Derived facts are always marked

```python
snapshot = owl.graph().subgraph("demo:Invoice/123", depth=2)
[e for e in snapshot.edges if e.inferred]   # what the reasoner concluded
snapshot.truncated                          # or did we just stop looking?
```

## Errors say why

Every failure is a typed `GraphOWLError` carrying the server's own explanation, as an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem document. A `403` that means "you need a capability" is a different class from a `401` that means "your key is wrong", because they need different fixes.

```python
from graphowl import RefusedError, NotFoundError

try:
    owl.governance.grant("bot", ["recordInvestigation"])
except RefusedError as e:
    print(e.status, e.title, e)
```

## Scope

The client covers the public API and also some administrative routes that the published [API description](https://github.com/graphowl/graphowl/blob/main/api/openapi.json) leaves out; those need an administrator's key.

## Tests

```bash
pip install pytest
pytest
```

The tests mock the transport, so they check this client against its own model of the server. Run something real before you trust it.

## Licence

[Apache-2.0](LICENSE). The GraphOWL name and logos are not covered by it; see the [brand terms](https://github.com/graphowl/graphowl/blob/main/brand/README.md).
