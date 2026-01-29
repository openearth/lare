<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:sld="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>fire</sld:Name>
      <sld:Title>Fire mitigation score</sld:Title>
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
              <sld:ColorMapEntry label="0.0000" quantity="0" color="#fff5f0"/>
              <sld:ColorMapEntry label="0.1000" quantity="0.10000000000000001" color="#fee5d9"/>
              <sld:ColorMapEntry label="0.2000" quantity="0.20000000000000001" color="#fdccb8"/>
              <sld:ColorMapEntry label="0.3000" quantity="0.30000000000000004" color="#fcae93"/>
              <sld:ColorMapEntry label="0.4000" quantity="0.40000000000000002" color="#fc8f6f"/>
              <sld:ColorMapEntry label="0.5000" quantity="0.5" color="#fb7050"/>
              <sld:ColorMapEntry label="0.6000" quantity="0.60000000000000009" color="#f44d38"/>
              <sld:ColorMapEntry label="0.7000" quantity="0.70000000000000007" color="#e12e26"/>
              <sld:ColorMapEntry label="0.8000" quantity="0.80000000000000004" color="#c5161c"/>
              <sld:ColorMapEntry label="0.9000" quantity="0.90000000000000002" color="#a50f15"/>
              <sld:ColorMapEntry label="1.0000" quantity="1" color="#67000d"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
