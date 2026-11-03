# Project instructions

## Database

- Use PostgreSQL in all environments. This includes development and tests.
- Do not use SQLite. Do not create SQLite test settings.
- Use a separate PostgreSQL database for tests. Do not run tests against application data.
- If PostgreSQL is not available, find the cause or report the problem. Do not change the database engine.

## Documentation

- Use ASD-STE100 Simplified Technical English for new and changed technical documentation.
- Apply the writing rules and the approved word meanings in the current issue. The reference for this change is Issue 9.
- Use active voice. Give one instruction in each sentence.
- Use a maximum of 20 words in a procedural sentence. Use a maximum of 25 words in a descriptive sentence.
- Use short paragraphs. Give one subject in each paragraph.
- Use American English spelling unless an exact project name or interface label has different spelling.
- Do not use contractions or semicolons in prose.
- Do not use a technical noun as a verb.
- Use the same term for the same item. Define each necessary technical name.
- Keep exact code names, field names, group names, file paths, and interface labels when necessary. Identify them as technical names.
- Check words against the STE dictionary. Check technical names against the rules for technical names.
- Include diagram labels, table text, and image descriptions in the language review.
- Do not state that a document complies with ASD-STE100 unless the full language review is complete.
- If the standard is not available, record this limit. Do not describe a partial language check as full compliance.
- For design work, identify proposals, assumptions, and open decisions. Do not present them as approved requirements.
- When the user requests documentation only, do not change application code, migrations, or deployed services.

The official reference is https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf.

## Code documentation

These rules apply throughout the project, including tests and private implementation code.

- Give every class, function, and method a docstring.
- Include constructors, factory methods, protocol methods, and test helpers.
- Describe the purpose of each class and callable.
- Document inputs, results, side effects, and exceptions where they are relevant.
- Add explanatory comments before conditional branches and guard clauses.
- Put a blank line before each explanatory comment or comment block.
- Include conditional expressions, comprehension filters, and conditional loop logic.
- Explain the reason for each condition and the behavior it protects.
- Explain separate branch outcomes when one comment does not cover them clearly.
- Keep docstrings and comments consistent with the implementation.
- Apply the project documentation language rules to docstrings and explanatory comments.

## Diary implementation tracking

- Update `Diary/TODO_V1.md` when Diary implementation changes.
- Keep each DV1 identifier unchanged.
- Name implementation files and exact classes, functions, or methods in the checklist annotations.
- Name verification files and exact test classes or methods.
- Add the same DV1 references to applicable source comments or docstrings.
- Identify template blocks, CSS selectors, or JavaScript functions for implementations without Python symbols.
- Keep partial items unchecked and describe the remaining work.
- Identify documentation-only items without inventing executable symbols.

## Diary UI

- Give each visible component, content role, form control, and task state a stable, descriptive CSS class.
- Use the `diary-` prefix and keep component rules within the `.diary` namespace.
- Use classes as the styling interface. Do not require IDs, text values, or element positions for host style overrides.
- Do not put presentation rules in inline style attributes.
- Document each styling class and CSS variable in `Diary/README.md`. Record the impact of changes to existing class names.

## Deployment

- Read `General Deployment Instructions` before work on this project.
- Commit and push task changes. Include the applicable documents, templates, static files, and migrations.
- Keep unrelated user changes.
