<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0" xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>flood</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ChannelSelection>
              <sld:GrayChannel>
                <sld:SourceChannelName>1</sld:SourceChannelName>
              </sld:GrayChannel>
            </sld:ChannelSelection>
            <sld:ColorMap type="ramp">
              <sld:ColorMapEntry color="#ffffff" quantity="-9999" label="Flood mitigation score" opacity="0.01" />
              <sld:ColorMapEntry quantity="0" label="0.0" color="#f7fbff"/>
              <sld:ColorMapEntry quantity="0.10000000000000001" label="0.1" color="#e4eff9"/>
              <sld:ColorMapEntry quantity="0.20000000000000001" label="0.2" color="#d1e2f3"/>
              <sld:ColorMapEntry quantity="0.30000000000000004" label="0.3" color="#bad6eb"/>
              <sld:ColorMapEntry quantity="0.40000000000000002" label="0.4" color="#9ac8e0"/>
              <sld:ColorMapEntry quantity="0.5" label="0.5" color="#73b2d8"/>
              <sld:ColorMapEntry quantity="0.60000000000000009" label="0.6" color="#529dcc"/>
              <sld:ColorMapEntry quantity="0.70000000000000007" label="0.7" color="#3585bf"/>
              <sld:ColorMapEntry quantity="0.80000000000000004" label="0.8" color="#1d6cb1"/>
              <sld:ColorMapEntry quantity="0.90000000000000002" label="0.9" color="#08519c"/>
              <sld:ColorMapEntry quantity="1" label="1.0" color="#08306b"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
