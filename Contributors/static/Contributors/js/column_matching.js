document.addEventListener("DOMContentLoaded", () => {

  const possibleMatches = JSON.parse(document.getElementById('csv-possible-matches').textContent) || {};
  const csvData = JSON.parse(document.getElementById('csv-data').textContent) || [];
  document.getElementById('csv-data-value').value = JSON.stringify(csvData);
  const columns = Array.from(new Set(csvData.flatMap(row => Object.keys(row))));
  const rows = csvData.map(row => columns.map(column => String(row[column] ?? '')));
  const sample = rows[0] || columns.map(() => '');
  const fields = [
    { key: 'contributor_name', label: 'Contributor name (required)' },
    { key: 'contact_name', label: 'Contact name' },
    { key: 'phone', label: 'Phone' },
    { key: 'email', label: 'Email' },
    { key: 'contact_history', label: 'Contact History' }
  ];
  const IGNORE = '__ignore__';
  const SOCIALS = '__socials__';
  const suggestions = columns.map(column => {
    const destination = Object.hasOwn(possibleMatches, column) ? possibleMatches[column] : '';
    return fields.some(field => field.key === destination) ? destination : '';
  });
  // Multiple suggestions for one field are ambiguous: leave all of them unmapped.
  const counts = new Map();
  suggestions.filter(Boolean).forEach(key => counts.set(key, (counts.get(key) || 0) + 1));
  suggestions.forEach((key, index) => { if (counts.get(key) > 1) suggestions[index] = ''; });
  const selects = new Map();
  const assignments = new Map(columns.map((column, index) => [column, suggestions[index]]));
  const statuses = new Map();
  const sampleCells = new Map();
  function changeAssignment(mapping, column, destination) {
    const owner = destination && destination !== IGNORE && destination !== SOCIALS
      ? Array.from(mapping.keys()).find(key => key !== column && mapping.get(key) === destination)
      : undefined;
    if (owner !== undefined) mapping.set(owner, '');
    mapping.set(column, destination);
    return owner;
  }
  const container = document.getElementById('mappings');
  columns.forEach((column, index) => {
    const row = document.createElement('div'); row.className = 'row';
    const label = document.createElement('label'); label.htmlFor = 'column-' + index;
    label.textContent = column;
    const controls = document.createElement('div');
    const select = document.createElement('select'); select.id = 'column-' + index;
    select.setAttribute('aria-label', 'Save CSV column ' + column + ' to');
    select.add(new Option('Choose where to save…', ''));
    select.add(new Option('Additional details (socials)', SOCIALS));
    select.add(new Option('Ignore — don’t upload', IGNORE));
    fields.forEach(field => select.add(new Option(field.label, field.key)));
    select.value = suggestions[index];
    const status = document.createElement('span'); status.className = 'status';
    status.id = select.id + '-status'; select.setAttribute('aria-describedby', status.id);
    controls.append(select, status);
    const sampleCell = document.createElement('div'); sampleCell.className = 'sample';
    sampleCell.textContent = sample[index] || 'Blank';
    sampleCells.set(column, sampleCell);
    row.append(label, sampleCell, controls); container.append(row);
    selects.set(column, select); statuses.set(column, status);
    select.addEventListener('change', () => {
      const destination = select.value;
      const owner = changeAssignment(assignments, column, destination);
      selects.forEach((control, key) => { control.value = assignments.get(key); });
      update();
      if (owner !== undefined) {
        const labelFor = key => fields.find(field => field.key === key)?.label || (key === IGNORE ? 'Ignore' : 'Additional details');
        const announcement = column + ' → ' + labelFor(destination) + '; ' + owner + ' is now not mapped and will not be imported.';
        const message = document.getElementById('message');
        message.textContent = announcement + (message.textContent ? ' ' + message.textContent : '');
      }
    });
  });
  function sourceFor(key) {
    return columns.find(column => selects.get(column).value === key);
  }
  function update() {
    sampleCells.forEach((cell, column) => { cell.textContent = sample[columns.indexOf(column)] || 'Blank'; });
    document.getElementById('column-mapping-value').value = JSON.stringify(Object.fromEntries(assignments));
    const selected = columns.map(column => selects.get(column).value).filter(value => value && value !== IGNORE && value !== SOCIALS);
    const ignored = columns.filter(column => selects.get(column).value === IGNORE);
    const unused = columns.filter(column => !selects.get(column).value);
    columns.forEach((column, index) => {
      const select = selects.get(column);
      Array.from(select.options).forEach(option => {
        const field = fields.find(field => field.key === option.value);
        if (!field) return;
        const owner = sourceFor(field.key);
        const occupied = owner !== undefined && owner !== column;
        option.disabled = false;
        option.className = occupied ? 'occupied' : owner === column ? 'current' : '';
        option.textContent = field.label + (occupied ? ' — currently: ' + owner : '');
      });
      const status = statuses.get(column);
      status.textContent = select.value === IGNORE ? 'Excluded from import' : !select.value ? 'Not mapped — not imported' : select.value === SOCIALS ? 'Saved as ' + column : select.value === suggestions[index] ? 'Suggested from CSV header' : 'Matched';
      select.parentElement.parentElement.classList.toggle('ignored', select.value === IGNORE);
      select.parentElement.parentElement.classList.toggle('mapped', Boolean(select.value && select.value !== IGNORE && select.value !== SOCIALS));
      select.parentElement.parentElement.classList.toggle('additional', select.value === SOCIALS);
    });
    const extras = columns.filter(column => selects.get(column).value === SOCIALS);
    document.getElementById('extra-count').textContent = extras.length + ' columns';
    const chips = document.getElementById('extras'); chips.replaceChildren();
    extras.forEach(column => { const chip = document.createElement('span'); chip.className = 'chip'; chip.textContent = column; chips.append(chip); });
    if (!extras.length) chips.textContent = 'No additional details to upload.';
    const head = document.getElementById('preview-head'); head.replaceChildren();
    const headingRow = document.createElement('tr');
    ['Row', ...fields.map(field => field.label), 'Additional details (socials)'].forEach(label => {
      const cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = label; headingRow.append(cell);
    });
    head.append(headingRow);
    const body = document.getElementById('preview-body'); body.replaceChildren();
    rows.forEach((values, index) => {
      const row = document.createElement('tr');
      const number = document.createElement('th'); number.scope = 'row'; number.textContent = String(index + 1); row.append(number);
      fields.forEach(field => {
        const cell = document.createElement('td');
        const source = sourceFor(field.key);
        const value = source === undefined ? '' : values[columns.indexOf(source)];
        cell.textContent = value;
        if (field.key === 'contributor_name' && !value.trim()) {
          cell.textContent = source === undefined ? 'Name not mapped' : 'Missing name';
          cell.className = 'missing-name';
        }
        row.append(cell);
      });
      const details = document.createElement('td');
      const json = document.createElement('pre');
      json.textContent = JSON.stringify(Object.fromEntries(extras.map(column => [column, values[columns.indexOf(column)]])), null, 2);
      details.append(json); row.append(details); body.append(row);
    });
    document.getElementById('preview-count').textContent = rows.length + ' rows';
    const hasName = selected.includes('contributor_name');
    document.getElementById('review').disabled = !hasName || !rows.length;
    document.getElementById('summary').textContent = (hasName ? 'Name matched' : 'Name match needed') + ' · ' + extras.length + ' additional details · ' + unused.length + ' unused · ' + ignored.length + ' ignored';
    document.getElementById('message').textContent = !rows.length ? 'The CSV contains no data rows. Upload a file with contributor data.' : hasName ? '' : 'Match one CSV column to Contributor name to continue. Contact name, phone and email are optional.';
  }
  document.getElementById('file-summary').textContent = rows.length + ' contributors · ' + columns.length + ' columns';
  document.getElementById('column-matching-form').addEventListener('submit', event => {
    if (!sourceFor('contributor_name') || !rows.length) event.preventDefault();
  });
  update();
});
