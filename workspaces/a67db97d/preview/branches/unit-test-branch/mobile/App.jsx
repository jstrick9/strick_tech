// Agentic OS — Expo React Native Web — Live Editable
// Edit this file in Monaco → iPhone preview hot-reloads instantly
// Uses: React 18 + react-native-web (via CDN, no build step)

const { useState } = React;
const { View, Text, Pressable, ScrollView, StyleSheet, TextInput } = ReactNativeWeb;

function ExpoApp() {
  const [count, setCount] = useState(0);
  const [tab, setTab] = useState('home');
  const [note, setNote] = useState('Built with Agentic OS v3.2');

  return (
    <View style={s.container}>
      <View style={s.header}>
        <Text style={s.htitle}>Agentic OS</Text>
        <Text style={s.hsub}>Expo • RN Web • Live HMR</Text>
      </View>

      <ScrollView style={{flex:1}} contentContainerStyle={{padding:18, paddingBottom:40}}>
        <View style={s.card}>
          <Text style={s.cardTitle}>🚀 Live Mobile App</Text>
          <Text style={s.cardDesc}>
            This is a real React Native app running via react-native-web.
            Edit <Text style={{fontFamily:'monospace', color:'#bb9af7'}}>mobile/App.jsx</Text> in Monaco →
            iPhone preview updates in ~600ms.
          </Text>

          <Pressable 
            style={({pressed})=>[s.btn, pressed && {opacity:.72}]}
            onPress={()=>setCount(c=>c+1)}
          >
            <Text style={s.btnT}>Tap • {count}</Text>
          </Pressable>

          <Text style={s.hint}>
            {count>0 ? `Tapped ${count}× @ ${new Date().toLocaleTimeString()}` : 'Waiting for tap…'}
          </Text>
        </View>

        <View style={{flexDirection:'row',gap:10,marginTop:14}}>
          {[
            ['⚡','Hermes', '#1a2333'],
            ['🧠','Claude', '#231a33'],
            ['📱','OpenClaw','#1a3323'],
          ].map(([ico,lab,bg])=>(
            <View key={lab} style={[s.pill,{backgroundColor:bg}]}>
              <Text style={s.pillT}>{ico} {lab}</Text>
            </View>
          ))}
        </View>

        <View style={[s.card,{marginTop:16}]}>
          <Text style={{color:'#cbd5ff', fontWeight:'700', marginBottom:8}}>Agent note</Text>
          <TextInput
            value={note}
            onChangeText={setNote}
            style={s.input}
            placeholder="Type here… HMR preserves state"
            placeholderTextColor="#5b647a"
          />
          <Text style={{color:'#7a8299', fontSize:11, marginTop:8}}>
            State persists across hot reloads. Try editing styles in Monaco →
          </Text>
        </View>

        <View style={[s.card,{marginTop:16, borderColor:'#2a3a1a'}]}>
          <Text style={{color:'#9ece6a', fontWeight:'700'}}>✓ Expo React Native Web</Text>
          <Text style={{color:'#8a9ab8', fontSize:12, marginTop:6, lineHeight:17}}>
            • View • Text • Pressable • ScrollView • TextInput{'\n'}
            • StyleSheet • flexbox = 100% RN API{'\n'}
            • No Metro, no Expo Go — runs in browser instantly{'\n'}
            • Agent OS → save → HMR → iPhone updates
          </Text>
        </View>
      </ScrollView>

      {/* iOS tab bar */}
      <View style={s.tabbar}>
        {[
          ['home','⌂','Home'],
          ['search','⌕','Search'],
          ['create','+', 'Build'],
          ['bell','◉','Alerts'],
          ['user','○','You'],
        ].map(([k,ico,label])=>(
          <Pressable key={k} onPress={()=>setTab(k)} style={{flex:1,alignItems:'center',paddingVertical:10}}>
            <Text style={[s.tabi, tab===k && s.tabiActive]}>{ico}</Text>
            <Text style={[s.tabLabel, tab===k && s.tabLabelActive]}>{label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  container:{ flex:1, backgroundColor:'#0b0d12' },
  header:{ paddingTop:8, paddingHorizontal:20, paddingBottom:14, backgroundColor:'#0f111a', borderBottomWidth:1, borderBottomColor:'#1d2233' },
  htitle:{ color:'#fff', fontSize:20, fontWeight:'800', letterSpacing:0.2 },
  hsub:{ color:'#7aa2f7', fontSize:12, marginTop:2 },
  card:{ backgroundColor:'#121629', borderRadius:20, padding:18, borderWidth:1, borderColor:'#222946' },
  cardTitle:{ color:'#fff', fontSize:18, fontWeight:'700', marginBottom:6 },
  cardDesc:{ color:'#9aa4bf', fontSize:13, lineHeight:18, marginBottom:14 },
  btn:{ backgroundColor:'#7aa2f7', borderRadius:12, paddingVertical:13, alignItems:'center', marginTop:4 },
  btnT:{ color:'#081028', fontWeight:'800', fontSize:15 },
  hint:{ color:'#9ece6a', fontSize:12, marginTop:10 },
  pill:{ flex:1, borderRadius:12, paddingVertical:10, alignItems:'center', borderWidth:1, borderColor:'#263250' },
  pillT:{ color:'#d5ddff', fontSize:12, fontWeight:'600' },
  input:{ backgroundColor:'#0f1528', color:'#e8efff', borderWidth:1, borderColor:'#263250', borderRadius:10, padding:12, fontSize:14 },
  tabbar:{ flexDirection:'row', borderTopWidth:1, borderTopColor:'#1d2233', backgroundColor:'#0f121c', paddingBottom:20 },
  tabi:{ color:'#5b647a', fontSize:20 },
  tabiActive:{ color:'#7aa2f7' },
  tabLabel:{ color:'#5b647a', fontSize:10, marginTop:2 },
  tabLabelActive:{ color:'#7aa2f7' },
});

// expose to Agentic OS preview loader
window.ExpoApp = ExpoApp;
console.log('[Agentic OS] mobile/App.jsx loaded — HMR ready');
