<?xml version="1.0" encoding="UTF-8"?><sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
    <sld:NamedLayer>
        <sld:Name>HRL_CPL:CTY_S2023</sld:Name>
        <sld:UserStyle>
            <sld:Name>CLMS_HRLVLCC_CTY</sld:Name>
            <sld:IsDefault>1</sld:IsDefault>
            <sld:FeatureTypeStyle>
                <sld:Name>name</sld:Name>
                <sld:Rule>
                    <sld:RasterSymbolizer>
                        <sld:ChannelSelection>
                            <sld:GrayChannel>
                                <sld:SourceChannelName>1</sld:SourceChannelName>
                                <sld:ContrastEnhancement>
                                    <sld:GammaValue>1.0</sld:GammaValue>
                                </sld:ContrastEnhancement>
                            </sld:GrayChannel>
                        </sld:ChannelSelection>
                        <sld:ColorMap type="values">
                            <sld:ColorMapEntry color="#f0f0f0" opacity="0" quantity="0" label="No Cropland"/>
                            <sld:ColorMapEntry color="#ee6e32" quantity="1110" label="Wheat"/>
                            <sld:ColorMapEntry color="#fba24a" quantity="1120" label="Barley"/>
                            <sld:ColorMapEntry color="#fadc14" quantity="1130" label="Maize"/>
                            <sld:ColorMapEntry color="#e94301" quantity="1140" label="Rice"/>
                            <sld:ColorMapEntry color="#e8a995" quantity="1150" label="Other Cereals"/>
                            <sld:ColorMapEntry color="#aec7e8" quantity="1210" label="Fresh Vegetables"/>
                            <sld:ColorMapEntry color="#4897bf" quantity="1220" label="Dry Pulses"/>
                            <sld:ColorMapEntry color="#c98c43" quantity="1310" label="Potatoes"/>
                            <sld:ColorMapEntry color="#9c5b0c" quantity="1320" label="Sugar Beet"/>
                            <sld:ColorMapEntry color="#ff7979" quantity="1410" label="Sunflower"/>
                            <sld:ColorMapEntry color="#a86a96" quantity="1420" label="Soybeans"/>
                            <sld:ColorMapEntry color="#e377c2" quantity="1430" label="Rapeseed"/>
                            <sld:ColorMapEntry color="#f7b6d2" quantity="1440" label="Flax cotton and hemp"/>
                            <sld:ColorMapEntry color="#dbdb8d" quantity="2100" label="Grapes"/>
                            <sld:ColorMapEntry color="#c1ce12" quantity="2200" label="Olives"/>
                            <sld:ColorMapEntry color="#79a03a" quantity="2310" label="Fruits"/>
                            <sld:ColorMapEntry color="#5a7c30" quantity="2320" label="Nuts"/>
                            <sld:ColorMapEntry color="#d7d7d7" quantity="3100" label="Unclassified arable crop"/>
                            <sld:ColorMapEntry color="#ababab" quantity="3200" label="Unclassified permanent crop"/>
                            <sld:ColorMapEntry color="#000000" opacity="0" quantity="65535" label="Outside area"/>
                        </sld:ColorMap>
                        <sld:ContrastEnhancement/>
                    </sld:RasterSymbolizer>
                </sld:Rule>
            </sld:FeatureTypeStyle>
        </sld:UserStyle>
    </sld:NamedLayer>
</sld:StyledLayerDescriptor>

