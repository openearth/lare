<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" version="1.0.0" xmlns:sld="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>Fire</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ChannelSelection>
              <sld:GrayChannel>
                <sld:SourceChannelName>1</sld:SourceChannelName>
              </sld:GrayChannel>
            </sld:ChannelSelection>
            <sld:ColorMap type="ramp">
              <sld:ColorMapEntry label="Fire Mitigation score" quantity="-9999" color="#fff5f0" opacity="0.01"/>
              <sld:ColorMapEntry quantity="0" label="0.0" opacity="0.01" color="#fff5f0"/>
              <sld:ColorMapEntry quantity="0.10000000000000001" label="0.1" color="#fee5d9"/>
              <sld:ColorMapEntry quantity="0.20000000000000001" label="0.2" color="#fdccb8"/>
              <sld:ColorMapEntry quantity="0.30000000000000004" label="0.3" color="#fcae93"/>
              <sld:ColorMapEntry quantity="0.40000000000000002" label="0.4" color="#fc8f6f"/>
              <sld:ColorMapEntry quantity="0.5" label="0.5" color="#fb7050"/>
              <sld:ColorMapEntry quantity="0.60000000000000009" label="0.6" color="#f44d38"/>
              <sld:ColorMapEntry quantity="0.70000000000000007" label="0.7" color="#e12e26"/>
              <sld:ColorMapEntry quantity="0.80000000000000004" label="0.8" color="#c5161c"/>
              <sld:ColorMapEntry quantity="0.90000000000000002" label="0.9" color="#a50f15"/>
              <sld:ColorMapEntry quantity="1" label="1.0" color="#67000d"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
