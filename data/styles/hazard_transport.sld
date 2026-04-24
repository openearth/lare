<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.1.0" xmlns:ogc="http://www.opengis.net/ogc" xmlns:se="http://www.opengis.net/se" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.1.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <se:Name>hexagons_coastal</se:Name>
    <UserStyle>
      <se:Name>hexagons_coastal</se:Name>
     <se:FeatureTypeStyle>
  <se:Rule>
    <se:Name>0 - 1000</se:Name>
    <se:Description>
      <se:Title>hazard_aggregated &gt; 0 and length between 0 and 1000</se:Title>
    </se:Description>
    <ogc:Filter>
      <ogc:And>
        <ogc:PropertyIsGreaterThan>
          <ogc:PropertyName>hazard_aggregated</ogc:PropertyName>
          <ogc:Literal>0</ogc:Literal>
        </ogc:PropertyIsGreaterThan>
        <ogc:PropertyIsGreaterThanOrEqualTo>
          <ogc:PropertyName>kcs_aggregation_length</ogc:PropertyName>
          <ogc:Literal>0</ogc:Literal>
        </ogc:PropertyIsGreaterThanOrEqualTo>
        <ogc:PropertyIsLessThanOrEqualTo>
          <ogc:PropertyName>kcs_aggregation_length</ogc:PropertyName>
          <ogc:Literal>1000</ogc:Literal>
        </ogc:PropertyIsLessThanOrEqualTo>
      </ogc:And>
    </ogc:Filter>
    <se:PolygonSymbolizer>
      <se:Fill>
        <se:SvgParameter name="fill">#eff3ff</se:SvgParameter>
      </se:Fill>
      <se:Stroke>
        <se:SvgParameter name="stroke">#000000</se:SvgParameter>
        <se:SvgParameter name="stroke-width">1</se:SvgParameter>
        <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
      </se:Stroke>
    </se:PolygonSymbolizer>
  </se:Rule>

  <se:Rule>
    <se:Name>1000 - 2500</se:Name>
    <se:Description>
      <se:Title>hazard_aggregated &gt; 0 and length between 1000 and 2500</se:Title>
    </se:Description>
    <ogc:Filter>
      <ogc:And>
        <ogc:PropertyIsGreaterThan>
          <ogc:PropertyName>hazard_aggregated</ogc:PropertyName>
          <ogc:Literal>0</ogc:Literal>
        </ogc:PropertyIsGreaterThan>
        <ogc:PropertyIsGreaterThan>
          <ogc:PropertyName>kcs_aggregation_length</ogc:PropertyName>
          <ogc:Literal>1000</ogc:Literal>
        </ogc:PropertyIsGreaterThan>
        <ogc:PropertyIsLessThanOrEqualTo>
          <ogc:PropertyName>kcs_aggregation_length</ogc:PropertyName>
          <ogc:Literal>2500</ogc:Literal>
        </ogc:PropertyIsLessThanOrEqualTo>
      </ogc:And>
    </ogc:Filter>
    <se:PolygonSymbolizer>
      <se:Fill>
        <se:SvgParameter name="fill">#bdd7e7</se:SvgParameter>
      </se:Fill>
      <se:Stroke>
        <se:SvgParameter name="stroke">#232323</se:SvgParameter>
        <se:SvgParameter name="stroke-width">1</se:SvgParameter>
        <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
      </se:Stroke>
    </se:PolygonSymbolizer>
  </se:Rule>

  <se:Rule>
    <se:Name>2500 - 5000</se:Name>
    <se:Description>
      <se:Title>hazard_aggregated &gt; 0 and length between 2500 and 5000</se:Title>
    </se:Description>
    <ogc:Filter>
      <ogc:And>
        <ogc:PropertyIsGreaterThan>
          <ogc:PropertyName>hazard_aggregated</ogc:PropertyName>
          <ogc:Literal>0</ogc:Literal>
        </ogc:PropertyIsGreaterThan>
        <ogc:PropertyIsGreaterThan>
          <ogc:PropertyName>kcs_aggregation_length</ogc:PropertyName>
          <ogc:Literal>2500</ogc:Literal>
        </ogc:PropertyIsGreaterThan>
        <ogc:PropertyIsLessThanOrEqualTo>
          <ogc:PropertyName>kcs_aggregation_length</ogc:PropertyName>
          <ogc:Literal>5000</ogc:Literal>
        </ogc:PropertyIsLessThanOrEqualTo>
      </ogc:And>
    </ogc:Filter>
    <se:PolygonSymbolizer>
      <se:Fill>
        <se:SvgParameter name="fill">#6baed6</se:SvgParameter>
      </se:Fill>
      <se:Stroke>
        <se:SvgParameter name="stroke">#232323</se:SvgParameter>
        <se:SvgParameter name="stroke-width">1</se:SvgParameter>
        <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
      </se:Stroke>
    </se:PolygonSymbolizer>
  </se:Rule>

  <se:Rule>
    <se:Name>&gt; 5000</se:Name>
    <se:Description>
      <se:Title>hazard_aggregated &gt; 0 and length &gt; 5000</se:Title>
    </se:Description>
    <ogc:Filter>
      <ogc:And>
        <ogc:PropertyIsGreaterThan>
          <ogc:PropertyName>hazard_aggregated</ogc:PropertyName>
          <ogc:Literal>0</ogc:Literal>
        </ogc:PropertyIsGreaterThan>
        <ogc:PropertyIsGreaterThan>
          <ogc:PropertyName>kcs_aggregation_length</ogc:PropertyName>
          <ogc:Literal>5000</ogc:Literal>
        </ogc:PropertyIsGreaterThan>
      </ogc:And>
    </ogc:Filter>
    <se:PolygonSymbolizer>
      <se:Fill>
        <se:SvgParameter name="fill">#2171b5</se:SvgParameter>
      </se:Fill>
      <se:Stroke>
        <se:SvgParameter name="stroke">#232323</se:SvgParameter>
        <se:SvgParameter name="stroke-width">1</se:SvgParameter>
        <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
      </se:Stroke>
    </se:PolygonSymbolizer>
  </se:Rule>
</se:FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
