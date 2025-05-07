let cardContainer;
let sidebar;

let selectedTag = {sidebar: null, card: null};

function setupCards() {
        /* Set up the Scroll Snap Change event - if supported - to colour the selected button */
        cardContainer.addEventListener('scrollsnapchange', function (event) {
            let target = event.snapTargetBlock;
            let tag = target.getAttribute('card_name')
            MirrorSelected(tag);
        });
}

function MirrorSelected( tag ) {
    if (selectedTag.sidebar != null)
    {
        selectedTag.card.classList.remove('selected');
        selectedTag.sidebar.classList.remove('selected');
    }
    let card = cardContainer.querySelector('[card_name="'+tag+'"]');
    let sidebar_entry = sidebar.querySelector('[item="'+tag+'"]');
    if (card != null)
        card.classList.add('selected');
    if (sidebar_entry != null)
        sidebar_entry.classList.add('selected');
    selectedTag = {sidebar: sidebar_entry, card : card}
}

function setupSideBar() {
    /* Web-53 - make the sidebar entry divs selectable in all cases (direct and non-direct) */

    /* Set up click handlers on the sidebar buttons */
    let sidebars_entries = sidebar.querySelectorAll('div.sidebar.entry');
    if (sidebars_entries.length === 0)
        return

    /* Flag to ensure the first non-direct is highlighted when the page loads */
    let first_found = false;

    for (let i = 0; i < sidebars_entries.length; i++)
    {
        /* Add a click handler to each of the side bar buttons so it jumps to the right 'card'/page */
        let entry = sidebars_entries[i];

        /* Make sure the real first sidebar card is marked as selected */
        if ( entry.matches(':not(.direct)') && !first_found) {
            MirrorSelected(entry.getAttribute('item'));
            first_found = true;
        }

        entry.addEventListener('click', function (event)
            {
                let target = event.target;

                /* Although the event handler is added to the sidebar.entry div, the event might be fired on
                  a child item, such as an icon or a label, so need to find the parent div
                 */
                while (target.nodeName != "DIV" || !target.matches(".sidebar.entry"))
                    target = target.parentElement;

                /* Extract the 'tag'/destination from the button */
                let item = target.getAttribute('item');

                /* For non-direct buttons - find and jump to the right card */
                if (target.matches(':not(.direct)')){
                    let card = cardContainer.querySelector('[card_name="'+item+'"]');
                    if (card != null)
                        card.scrollIntoView({behavior:"smooth"});
                    MirrorSelected(item);
                }
                else {
                    /* For direct buttons - if the item attribute is set, then load that as a url */
                    if (item != null)
                        window.location.href = item
                }
            })
        }
    }

/* Set up the cards and buttons once the document is loaded */
addEventListener("DOMContentLoaded", function () {
        cardContainer = document.getElementById("CardContainer");
        sidebar = document.getElementById('SidebarContainer');
        setupSideBar();
        setupCards();
    }
 )
