
class GoogleMap {
    map = null;
    marker_details = { location:null, title :null};
    read_only = false;
    options = {
        center: {lat:0, lng:0},
        zoom: 12,
        control_size: 20,
        scale_control: true,
        fullscreenControl: true,
        zoomControl: true ,
        zoomControlOptions: {
            position: google.maps.ControlPosition.BLOCK_START_INLINE_END
        },
        streetViewControl: false,
        mapTypeControl: true,
        mapTypeControlOptions: {
            style: google.maps.MapTypeControlStyle.DROPDOWN_MENU,
            mapTypeIds: ["roadmap", "satellite", "hybrid"],
        }
    }

        constructor(element, marker_details, google_map_id, options = {}) {
            this.element = element;
            this.marker_details = marker_details;
            this.options.mapId = google_map_id;
            if (Object.keys(options) != 0)
                this.options = Object.assign({}, this.options, options);

        }

        display() {
            let wrapper =this.element.getElementsByClassName('map_wrapper');
            if (wrapper == null) {
                console.log('Cannot find the map_wrapper element for' + element.id)
                return
            }

            this.map = new google.maps.Map(wrapper[0],
                this.options);

            if (this.marker_details.location != null) {
                this.map.setZoom(18);
                this.map.panTo(JSON.parse(this.marker_details.location))
                this._addMarker(JSON.parse(this.marker_details.location), this.marker_details.title);
            }
        }

        _addMarker(location, title) {
            this.map.panTo(location);

            this.marker = new google.maps.marker.AdvancedMarkerElement({
                map: this.map,
                position: location,
                title: title,
            });
        }
    }