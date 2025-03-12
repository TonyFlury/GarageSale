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
    /* Set up click handlers on the side bar buttons */
    let sidebars_entries = sidebar.querySelectorAll('div.sidebar.entry:not(.direct)');
    if (sidebars_entries.length == 0)
        return

    for (let i = 0; i < sidebars_entries.length; i++)
    {
        /* Add a click handler to each of the side bar buttons so it jumps to the right 'card' */
        let entry = sidebars_entries[i];

        if (i === 0)
            MirrorSelected(entry.getAttribute('item'));

        entry.addEventListener('click', function (event)
            {
                let target = event.target;
                /* Look for the parent div */
                while (target.nodeName != "DIV" || !target.matches(".sidebar.entry"))
                    target = target.parentElement;

                /* Extract the 'tag' from the button */
                let item = target.getAttribute('item');

                let card = cardContainer.querySelector('[card_name="'+item+'"]');
                if (card != null)
                    card.scrollIntoView({behavior:"smooth"});
                MirrorSelected(item);
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
