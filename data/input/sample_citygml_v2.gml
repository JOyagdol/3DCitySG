<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel
    xmlns:core="http://www.opengis.net/citygml/2.0"
    xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
    xmlns:gml="http://www.opengis.net/gml">
  <core:cityObjectMember>
    <bldg:Building gml:id="bldg_1">
      <bldg:interiorRoom>
        <bldg:Room gml:id="room_1">
          <bldg:boundedBy>
            <bldg:WallSurface gml:id="wall_1">
              <bldg:opening>
                <bldg:Door gml:id="door_1" />
              </bldg:opening>
            </bldg:WallSurface>
          </bldg:boundedBy>
          <bldg:interiorFurniture>
            <bldg:BuildingFurniture gml:id="furn_1">
              <bldg:class>chair</bldg:class>
              <bldg:function>seating</bldg:function>
              <bldg:usage>office</bldg:usage>
            </bldg:BuildingFurniture>
          </bldg:interiorFurniture>
        </bldg:Room>
      </bldg:interiorRoom>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
