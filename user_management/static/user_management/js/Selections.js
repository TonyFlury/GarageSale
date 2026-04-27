{

    const SelectBox = {
        cache: {},
        init: function(id) {
            const box = document.getElementById(id);
            console.log('init : ' + id, box);
            SelectBox.cache[id] = [];
            const cache = SelectBox.cache[id];
            for (const node of box.options) {
                cache.push({value: node.value, text: node.text, displayed: 1});
            }
        },
        redisplay: function(id) {
            // Repopulate HTML select box from cache
            const box = document.getElementById(id);
            const scroll_value_from_top = box.scrollTop;
            box.innerHTML = '';
            for (const node of SelectBox.cache[id]) {
                if (node.displayed) {
                    const new_option = new Option(node.text, node.value, false, false);
                    // Shows a tooltip when hovering over the option
                    new_option.title = node.text;
                    box.appendChild(new_option);
                }
            }
            box.scrollTop = scroll_value_from_top;
        },
        filter: function(id, text) {
            // Redisplay the HTML select box, displaying only the choices containing ALL
            // the words in text. (It's an AND search.)
            const tokens = text.toLowerCase().split(/\s+/);
            for (const node of SelectBox.cache[id]) {
                node.displayed = 1;
                const node_text = node.text.toLowerCase();
                for (const token of tokens) {
                    if (!node_text.includes(token)) {
                        node.displayed = 0;
                        break; // Once the first token isn't found we're done
                    }
                }
            }
            SelectBox.redisplay(id);
        },
        get_hidden_node_count(id) {
            const cache = SelectBox.cache[id] || [];
            return cache.filter(node => node.displayed === 0).length;
        },
        delete_from_cache: function(id, value) {
            let delete_index = null;
            const cache = SelectBox.cache[id];
            for (const [i, node] of cache.entries()) {
                if (node.value === value) {
                    delete_index = i;
                    break;
                }
            }
            cache.splice(delete_index, 1);
        },
        add_to_cache: function(id, option) {
            SelectBox.cache[id].push({value: option.value, text: option.text, displayed: 1});
        },
        cache_contains: function(id, value) {
            // Check if an item is contained in the cache
            for (const node of SelectBox.cache[id]) {
                if (node.value === value) {
                    return true;
                }
            }
            return false;
        },
        move: function(from, to) {
            const from_box = document.getElementById(from);
            for (const option of from_box.options) {
                const option_value = option.value;
                if (option.selected && SelectBox.cache_contains(from, option_value)) {
                    SelectBox.add_to_cache(to, {value: option_value, text: option.text, displayed: 1});
                    SelectBox.delete_from_cache(from, option_value);
                }
            }
            SelectBox.redisplay(from);
            SelectBox.redisplay(to);
        },
        move_all: function(from, to) {
            const from_box = document.getElementById(from);
            for (const option of from_box.options) {
                const option_value = option.value;
                if (SelectBox.cache_contains(from, option_value)) {
                    SelectBox.add_to_cache(to, {value: option_value, text: option.text, displayed: 1});
                    SelectBox.delete_from_cache(from, option_value);
                }
            }
            SelectBox.redisplay(from);
            SelectBox.redisplay(to);
        },
        sort: function(id) {
            SelectBox.cache[id].sort(function(a, b) {
                a = a.text.toLowerCase();
                b = b.text.toLowerCase();
                if (a > b) {
                    return 1;
                }
                if (a < b) {
                    return -1;
                }
                return 0;
            } );
        },
        select_all: function(id) {
            const box = document.getElementById(id);
            for (const option of box.options) {
                option.selected = true;
            }
        }
    };
    window.SelectBox = SelectBox;

    window.SelectFilter = {
         init : function(field_id, field_name, is_stacked) {
             let base_id = field_id.slice(0, field_id.lastIndexOf('_'));
             console.log('base_id : ' + base_id);
             let from_box = window.document.getElementById(base_id + '_from');

             let choose_all = window.document.getElementById(base_id + '_add_all_link');
             let add_link = window.document.getElementById(base_id + '_add_link');
             let remove_link = window.document.getElementById(base_id + '_remove_link');
             let clear_all = window.document.getElementById(base_id + '_remove_all_link');

              const move_selection = function(e, elem, move_func, from, to) {
                if (elem.classList.contains('active')) {
                    move_func(from, to);
                    SelectFilter.refresh_icons(base_id);
                }
                e.preventDefault();  };

            let selector_div = document.querySelector('div.selector');

            selector_div.addEventListener('change', function(e) {
                if (e.target.tagName === 'SELECT') {
                    SelectFilter.refresh_icons(base_id);
                }
            });

            choose_all.addEventListener('click', function(e) {
                move_selection(e, this, SelectBox.move_all, base_id + '_from', base_id + '_to');
            });
            add_link.addEventListener('click', function(e) {
                move_selection(e, this, SelectBox.move, base_id + '_from', base_id + '_to');
            });
            remove_link.addEventListener('click', function(e) {
                move_selection(e, this, SelectBox.move, base_id + '_to', base_id + '_from');
            });
            clear_all.addEventListener('click', function(e) {
                move_selection(e, this, SelectBox.move_all, base_id + '_to', base_id + '_from');
            });

            selector_div.addEventListener('dblclick', function(e) {
                if (e.target.tagName === 'OPTION') {
                    if (e.target.closest('select').id === base_id + '_to') {
                        SelectBox.move(base_id + '_to', base_id + '_from');
                    } else {
                        SelectBox.move(base_id + '_from', base_id + '_to');
                    }
                    SelectFilter.refresh_icons(base_id);
                }
            });

            from_box.closest('form').addEventListener('submit', function() {
                SelectBox.filter(base_id + '_to', '');
                SelectBox.select_all(base_id + '_to');
            });

            SelectBox.init(base_id + '_from');
            SelectBox.init(base_id + '_to');

            // Move anything already selected
            SelectBox.move(base_id + '_from', base_id + '_to');
            // Initial icon refresh
            SelectFilter.refresh_icons(base_id);
         },

        any_selected: function(field) {
            // Temporarily add the required attribute and check validity.
            field.required = true;
            const any_selected = field.checkValidity();
            field.required = false;
            return any_selected;
        },

        refresh_icons: function(field_id) {
            const from = document.getElementById(field_id + '_from');
            const to = document.getElementById(field_id + '_to');
            // Active if at least one item is selected
            document.getElementById(field_id + '_add_link').classList.toggle('active', SelectFilter.any_selected(from));
            document.getElementById(field_id + '_remove_link').classList.toggle('active', SelectFilter.any_selected(to));
            // Active if the corresponding box isn't empty
            document.getElementById(field_id + '_add_all_link').classList.toggle('active', from.querySelector('option'));
            document.getElementById(field_id + '_remove_all_link').classList.toggle('active', to.querySelector('option'));
        },

    }

    window.addEventListener('load', function(e) {
        document.querySelectorAll('select.selectfilter, select.selectfilterstacked').forEach(function(el) {
            const data = el.dataset;
            SelectFilter.init(el.id, data.fieldName, parseInt(data.isStacked, 10));
        });
    });
}
