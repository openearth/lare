<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0" xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>erosion</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ChannelSelection>
              <sld:GrayChannel>
                <sld:SourceChannelName>1</sld:SourceChannelName>
              </sld:GrayChannel>
            </sld:ChannelSelection>
            <sld:ColorMap type="ramp">
              <sld:ColorMapEntry quantity="-9999" label="Erosion mitigation score" color="#ffffff" opacity="0.01"/>
              <sld:ColorMapEntry quantity="0" label="0.0" color="#018571"/>
              <sld:ColorMapEntry quantity="0.10000000000000001" label="0.1" color="#34a291"/>
              <sld:ColorMapEntry quantity="0.20000000000000001" label="0.2" color="#67bfb1"/>
              <sld:ColorMapEntry quantity="0.30000000000000004" label="0.3" color="#97d5cb"/>
              <sld:ColorMapEntry quantity="0.40000000000000002" label="0.4" color="#c6e5e0"/>
              <sld:ColorMapEntry quantity="0.5" label="0.5" color="#f5f5f5"/>
              <sld:ColorMapEntry quantity="0.60000000000000009" label="0.6" color="#ece1c5"/>
              <sld:ColorMapEntry quantity="0.70000000000000007" label="0.7" color="#e3cc95"/>
              <sld:ColorMapEntry quantity="0.80000000000000004" label="0.8" color="#d4af69"/>
              <sld:ColorMapEntry quantity="0.90000000000000002" label="0.9" color="#bd8842"/>
              <sld:ColorMapEntry quantity="1" label="1.0" color="#a6611a"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
