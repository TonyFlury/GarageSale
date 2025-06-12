
class GoogleMap {
    map = null;
    markers = [];
    read_only = false;
    DefaultOptions = {
        center: {lat: 0, lng: 0},
        zoom: 12,
        control_size: 20,
        scale_control: true,
        fullscreenControl: true,
        zoomControl: true,
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

    get defaultOptions() {
        return this.DefaultOptions;
    }

    constructor(element, markers, read_only, google_map_id) {
        this.options = Object.assign({}, this.DefaultOptions)
        this.read_only = read_only;
        if (!this.read_only && markers.length > 1)
            throw "Can't have a writable map with multiple markers"

        this.options.mapId = google_map_id;
        this.element = element;
        this.markers = markers;
        this.map_markers = []
    }

    set Options(new_options) {
        this.options = Object.assign(this.options, new_options );
    }

    pan_to(location, zoom=4){
        this.map.setZoom(zoom);
        this.map.panTo(location);
    }

    addMarker(location, title, pan_map=false) {
        if (this.markers.length > 1)
            pan_map = false ;
        this.markers.push({location, title});
        this.map_markers.push(this._addMarker(location, title, pan_map));
    }

    _addMarker(location, title, pan_map=false) {

        if (pan_map) {
            this.map.setZoom(18);
            this.map.panTo(location)
        }

        let marker = new google.maps.marker.AdvancedMarkerElement({
            map: this.map,
            position: location,
            title: title,
        });
        return marker
    }

    display( bounds = {} ) {
        let wrapper =this.element.getElementsByClassName('map_wrapper');
        if (wrapper == null) {
            console.log('Cannot find the map_wrapper element for' + element.id)
            return
        }

        this.map = new google.maps.Map(wrapper[0],
            this.options);

        if (Object.keys(bounds) != 0){
            this.map.setOptions({
                restriction: {
                        latLngBounds: bounds ,
                       strictBounds : true  } } );
       }

        if (this.markers.length == 1) {
            if (this.markers[0].location != null) {
                this.map_markers.push(this._addMarker(JSON.parse(this.markers[0].location),
                    this.markers[0].title, true));
            }
        }
        else {
            for (let i = 0; i < this.markers.length; i++) {
                this.map_markers.push(this._addMarker(JSON.parse(this.markers[i].location),
                    this.markers[i].title));
            }
        }
    }
}