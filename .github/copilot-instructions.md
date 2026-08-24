<SecurityRequirements>
- IMPORTANT: Follow Test Driven Development (TDD) AT ALL TIMES
  - Write the test first. Watch it fail. Write minimal code to pass.
  - Core principle: If you didn't watch the test fail, you don't know if it tests the right thing.
  - IRON LAW: NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
  No exceptions:
    Don't keep it as "reference"
    Don't "adapt" it while writing tests
    Don't look at it
    Delete means delete
- Use vulnerability free docker dhi image as a base "dhi.io/python:3-debian13-sfw-dev"
- Do not store any keys or secrets in code EVER
- Minimize the number of dependencies to reduce vulnerabilities
- As much as possible use dependencies that are latest-1 version. DO NOT USE  old packages with, BUT ALSO DO NOT USE "latest" package versions  that may have 0-days.
- Explisitly specify package versions in requirements.txt 
</SecurityRequirements>

<!-- SPECKIT START -->
## Current Implementation Plan

**Active Feature**: 003-wire-rss-react-ui  
**Plan**: [specs/003-wire-rss-react-ui/plan.md](../specs/003-wire-rss-react-ui/plan.md)

Review the plan for:
- Technical context and architecture decisions
- Data model and entity relationships (see [data-model.md](../specs/003-wire-rss-react-ui/data-model.md))
- API contracts (see [contracts/](../specs/003-wire-rss-react-ui/contracts/))
- Development workflow and TDD requirements (see [quickstart.md](../specs/003-wire-rss-react-ui/quickstart.md))
<!-- SPECKIT END -->