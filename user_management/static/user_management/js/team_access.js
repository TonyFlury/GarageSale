document.addEventListener('DOMContentLoaded', () => {
    const responsibilities = document.getElementById('access-responsibilities');
    const note = document.getElementById('volunteer-profile-only');
    if (!responsibilities || !note) return;
    const updateMembership = () => {
        const volunteer = document.querySelector('input[name="membership"]:checked')?.value === 'volunteer';
        responsibilities.hidden = volunteer;
        responsibilities.disabled = volunteer;
        note.hidden = !volunteer;
        if (volunteer) responsibilities.querySelectorAll('input[name="roles"]').forEach(input => { input.checked = false; });
    };
    document.querySelectorAll('input[name="membership"]').forEach(input => input.addEventListener('change', updateMembership));
    updateMembership();
});
