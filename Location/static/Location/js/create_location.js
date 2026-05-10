
        function help_popup() {
            const popup = document.getElementById("MapInstructions")
            popup.left = (window.innerWidth - popup.clientWidth) / 2;
            popup.top = (window.innerHeight - popup.clientHeight) / 2;
            popup.showModal();
            const help_button = document.getElementById("HelpIcon");
            help_button.style.display = "none";
        }

        function dialog_close() {
            const popup = document.getElementById("MapInstructions")
            if (popup.open) popup.close();
            const help_button = document.getElementById("HelpIcon");
            help_button.style.display = "inline-block";
        }

        function address_section_valid()
        {
            /** confirm if the address section is valid */
            let section1_fields = ["AdBoard", "HouseNumber", "StreetName", "Postocde", "Town" ];

            for (let i = 0; i < section1_fields.length; i++) {
                let section = section1_fields[i] + "Error"
                let item = document.getElementById(section)
                console.log(item, section)
                if (item.innerHTML.trim() !== '')
                    return false;
            }
            return true;
        }

        function map_section_valid(){
            let error = document.getElementById('MapError').innerHTML.trim()
            if (error === '')
                return true;

            return false;
        }

        function make_section_visible(section_id) {
            const section_to_hide = (section_id === "section1") ? "section2" : "section1";
            document.getElementById(section_to_hide).style.display = "none";
            document.getElementById(section_id).style.display = "block";
        }

        document.addEventListener("DOMContentLoaded", function() {

            /* form loads with the address section open */
            const popup = document.getElementById("MapInstructions")
            popup.addEventListener('close', dialog_close)

            if (!address_section_valid() )
                return;

            if (map_section_valid())
                return;

            make_section_visible("section2");
        });