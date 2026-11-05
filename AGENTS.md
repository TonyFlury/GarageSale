# Project instructions

## Database

- Use PostgreSQL in all environments, including development and tests.
- Do not use SQLite. Do not create SQLite test settings.
- Use a separate PostgreSQL database for tests. Do not run tests against application data.
- If PostgreSQL is not available, find the cause or report the problem. Do not change the database engine.

## Function size and helpers

- Keep each function and method short and focused on one responsibility.
- Extract named helpers for separate selection, validation, presentation, and side effects.
- Keep orchestration methods, including `get_context_data()`, limited to the main steps.
- Give each helper a clear responsibility and a descriptive name.
- Preserve the order of authorization, validation, and side effects during refactoring.

## Documentation

- Use ASD-STE100 Simplified Technical English for new and changed technical documentation.
- Apply the writing rules and approved word meanings in the current issue. The reference for this change is Issue 9.
- Use active voice. Give one instruction in each sentence.
- Use a maximum of 20 words in a procedural sentence.
- Use a maximum of 25 words in a descriptive sentence.
- Use short paragraphs. Give one subject in each paragraph.
- Use American English spelling unless an exact project name or interface label has different spelling.
- Do not use contractions or semicolons in prose.
- Do not use a technical noun as a verb.
- Use the same term for the same item. Define each necessary technical name.
- Keep exact code names, field names, group names, file paths, and interface labels when necessary.
- Identify these exact names as technical names.
- Check words against the STE dictionary. Check technical names against the rules for technical names.
- Include diagram labels, table text, and image descriptions in the language review.
- Do not state that a document complies with ASD-STE100 unless the full language review is complete.
- If the standard is not available, record this limit.
- Do not describe a partial language check as full compliance.
- For design work, identify proposals, assumptions, and open decisions.
- Do not present proposals as approved requirements.
- When the user requests documentation only, do not change application code, migrations, or deployed services.

The official reference is https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf.

## Code documentation

These rules apply throughout the project, including tests and private implementation code.

- Give every class, function, and method a docstring.
- Include constructors, factory methods, protocol methods, and test helpers.
- Describe the purpose of each class and callable.
- Document inputs, results, side effects, and exceptions where relevant.
- Add explanatory comments before conditional branches and guard clauses.
- Put a blank line before each explanatory comment or comment block.
- Include conditional expressions, comprehension filters, and conditional loop logic.
- Explain the reason for each condition and the behavior it protects.
- Explain separate branch outcomes when one comment does not cover them clearly.
- Keep docstrings and comments consistent with the implementation.
- Apply the project documentation language rules to docstrings and explanatory comments.

## Diary dependency boundary

- Treat the Diary app, distributed as DjangoTaskCalendar, as a third-party dependency.
- Diary owns its requirements, implementation, tests, release documentation, and backlog in its separate repository.
- Garage Sale owns its integration code, host configuration, presentation adaptations, deployment integration, and compatibility tests.
- Include only Garage Sale integration requirements in this project's feature lists and completion reports.
- Exclude Diary package requirements, defects, release checks, and backlog items from Garage Sale outstanding work.
- Identify package limitations separately when they affect a Garage Sale integration requirement.
- Use the installed package's public API and documented extension interfaces.
- Adapt Garage Sale integration code when an approved Diary update changes those interfaces.
- Do not modify installed Diary code or its separate repository during Garage Sale work without an explicit request.
- Do not update `Diary/TODO_V1.md` or package documentation for Garage Sale integration changes.
- Do not copy package forms, templates, or business logic into Garage Sale to bypass the dependency boundary.

## Diary host integration tracking

- Record host integration requirements and status in `GarageSale/DIARY_INTEGRATION.md`.
- Keep existing HOST identifiers unchanged.
- Name implementation files, exact symbols, and applicable verification in checklist annotations.
- Identify template blocks, CSS selectors, or JavaScript functions for implementations without Python symbols.
- Keep partial items unchecked and give each an explicit Remaining annotation.
- Distinguish approved requirements from proposed interfaces and open decisions.
- Identify documentation-only items without inventing executable symbols.

## Diary host UI

- Give each visible component, content role, form control, and task state a stable, descriptive CSS class.
- Use the `diary-` prefix. Keep component rules within the `.diary` namespace.
- Use classes as the styling interface.
- Do not require IDs, text values, or element positions for host style overrides.
- Do not put presentation rules in inline style attributes.
- Document host styling classes and CSS variables in `GarageSale/DIARY_INTEGRATION.md`.
- Preserve package styling interfaces and record the impact of host class changes.

Language review limit: The new dependency rules have not received a full ASD-STE100 Issue 9 dictionary review.

## Deployment

- Read `General Deployment Instructions` before work on this project.
- Commit and push task changes. Include applicable documents, templates, static files, and migrations.
- Keep unrelated user changes.
